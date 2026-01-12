#!/usr/bin/env python3
"""
IO CLI - THE SINGLE ENTRY POINT for Investigation Operations

This is the unified interface for:
1. EXECUTION - Run investigations via prefix operators (p:, c:, e:, t:, d:) or LINKLATER operator syntax
2. ROUTING - Lookup what inputs/outputs are available
3. C0GN1T0 API - Programmatic interface for investigation planning

EXECUTION MODE (prefix operators + LINKLATER operators + MACROS):
  io_cli.py "p: John Smith"                        # Full person investigation
  io_cli.py "p: John Smith" --results-viz          # Investigation + results graph
  io_cli.py "c: Acme Corp" --jurisdiction US       # Company investigation (filtered)
  io_cli.py "e: john@acme.com"                     # Email investigation
  io_cli.py "t: +1-555-1234"                       # Phone investigation
  io_cli.py "d: acme.com"                          # Domain investigation
  io_cli.py "p: John Smith" --dry-run              # Show plan without executing
  io_cli.py "?bl:!acme.com"                        # Linklater backlinks (domains)
  io_cli.py "bl?:!acme.com"                        # Linklater backlinks (pages)
  io_cli.py "ent?:2024! !acme.com"                 # Linklater historical entities
  io_cli.py "pdf!:!acme.com"                       # Linklater file discovery
  io_cli.py "\"keyword\" :tor"                     # Linklater Tor search

MACRO OPERATORS:
  io_cli.py "cdom? Acme Corp"                      # Find company website/domain
  io_cli.py "alldom? example.com"                  # Full domain analysis (Linklater)
  io_cli.py "crel? Acme Corp" --domain acme.com    # Find related companies
  io_cli.py "age? John Smith"                      # Find person age/DOB
  io_cli.py "rep? Acme Corp"                       # Reputation analytics
  io_cli.py --macro-logs                           # View recent macro execution logs

ROUTING MODE (lookup capabilities):
  io_cli.py --have email                           # What can I get from an email?
  io_cli.py --have email --want company_officers   # How to get officers from email?
  io_cli.py --graph domain --depth 2               # Graph data centered on domain
  io_cli.py --viz email --depth 2                  # Source capability graph (opt-in)
  io_cli.py --stats                                # Matrix statistics
  io_cli.py --legend company                       # Search field names

MODULE INFO:
  io_cli.py --list-modules                         # Show available execution modules
  io_cli.py --module-info eye-d                    # Details about EYE-D module

Prefixes:
  p: = person    c: = company    e: = email    t: = phone    d: = domain    u: = username    li: = linkedin_url    liu: = linkedin_username
  social media prefixes: fb:, facebook:, tw:, twitter:, x:, ig:, instagram:, threads:, social:, all:
  linklater operators: ?bl, bl?, ?ol, ol?, ent?, p?, c?, t?, e?, a?, pdf!, doc!, word!, xls!, ppt!, file!
  macro operators: cdom?, alldom?, crel?, age?, rep?
"""

import sys
import argparse
import json
import tempfile
import webbrowser
import asyncio
import os
import re
import logging
import subprocess
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from collections import deque, defaultdict
from datetime import datetime

# Repository root (works regardless of current working directory)
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Ensure repository root is importable (brute, eyed, TORPEDO, etc.)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Matrix data directory (same dir as this script)
MATRIX_DIR = Path(__file__).parent

# Macros directory (at repository root)
MACROS_DIR = Path(__file__).parent.parent.parent.parent / "macros"

# IO Logs directory (for macro I/O logging)
IO_LOGS_DIR = MATRIX_DIR / "logs"
IO_LOGS_DIR.mkdir(exist_ok=True)

# Logger for this module
logger = logging.getLogger("io_cli")

# Import IOCompiler from modular io_compiler.py
try:
    from io_compiler import IOCompiler, UnifiedSource
    IO_COMPILER_AVAILABLE = True
except ImportError:
    IO_COMPILER_AVAILABLE = False
    IOCompiler = None
    UnifiedSource = None

# Backend modules path (prefer SEARCH_ENGINEER/nexus layout if present)
_BACKEND_CANDIDATES = [
    PROJECT_ROOT / "SEARCH_ENGINEER" / "nexus" / "BACKEND" / "modules",
    PROJECT_ROOT / "BACKEND" / "modules",
]
BACKEND_PATH = next((p for p in _BACKEND_CANDIDATES if p.exists()), PROJECT_ROOT)
if BACKEND_PATH.exists() and str(BACKEND_PATH) not in sys.path:
    # Keep repo root higher priority to avoid shadowing top-level packages (e.g., LINKLATER/api.py).
    sys.path.insert(1, str(BACKEND_PATH))


def resolve_io_integration_path() -> Path:
    """Resolve IO_INTEGRATION.json location across repo layouts."""
    env_path = os.environ.get("IO_INTEGRATION_PATH")
    if env_path:
        p = Path(env_path).expanduser()
        if p.exists():
            return p

    candidates = [
        PROJECT_ROOT / "CYMONIDES" / "metadata" / "index_registry" / "IO_INTEGRATION.json",
        PROJECT_ROOT
        / "SEARCH_ENGINEER"
        / "nexus"
        / "MODULES"
        / "CYMONIDES"
        / "metadata"
        / "index_registry"
        / "IO_INTEGRATION.json",
        BACKEND_PATH / "CYMONIDES" / "metadata" / "index_registry" / "IO_INTEGRATION.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]

# Load environment variables from project root
ENV_FILE = PROJECT_ROOT / ".env"
if ENV_FILE.exists():
    from dotenv import load_dotenv
    load_dotenv(ENV_FILE)


# SASTRE Investigation Planner integration
try:
    from SASTRE.investigation_planner import (
        InvestigationPlanner,
        QueryGenerator,
        plan_from_tasking,
        generate_queries,
        get_route_summary,
    )
    SASTRE_AVAILABLE = True
except ImportError:
    SASTRE_AVAILABLE = False


# Reality Engine Integration
try:
    from SASTRE.grid.event_assessor import EventAssessor
    from SASTRE.grid.gap_executor import GapExecutor
    REALITY_ENGINE_AVAILABLE = True
except ImportError:
    try:
        # Try path relative to python-backend if not in path
        sys.path.insert(0, str(BACKEND_PATH / "modules"))
        from SASTRE.grid.event_assessor import EventAssessor
        from SASTRE.grid.gap_executor import GapExecutor
        REALITY_ENGINE_AVAILABLE = True
    except ImportError:
        REALITY_ENGINE_AVAILABLE = False


# LINKLATER operator execution
try:
    from query_parser import parse_query as parse_linklater_query
    LINKLATER_PARSER_AVAILABLE = True
except ImportError:
    parse_linklater_query = None
    LINKLATER_PARSER_AVAILABLE = False

try:
    from query_executor import QueryExecutor as LinklaterQueryExecutor
    LINKLATER_EXECUTOR_AVAILABLE = True
except ImportError:
    LinklaterQueryExecutor = None
    LINKLATER_EXECUTOR_AVAILABLE = False


# CookbookExecutor - Reactive slot-based investigation (replaces hardcoded pipelines)
try:
    # Ensure matrix dir is in path for cookbook_executor import
    _matrix_dir = str(Path(__file__).parent)
    if _matrix_dir not in sys.path:
        sys.path.insert(0, _matrix_dir)
    from cookbook_executor import CookbookExecutor, execute_company_dd, execute_person_dd
    COOKBOOK_EXECUTOR_AVAILABLE = True
except ImportError as _cookbook_err:
    logger.debug(f"CookbookExecutor not available: {_cookbook_err}")
    CookbookExecutor = None
    execute_company_dd = None
    execute_person_dd = None
    COOKBOOK_EXECUTOR_AVAILABLE = False


# ALLDOM Native WHOIS Bridge - Replaces basic python-whois with WhoisXML API
try:
    # Add ALLDOM path
    _alldom_path = BACKEND_PATH / "alldom"
    if _alldom_path.exists() and str(_alldom_path.parent) not in sys.path:
        sys.path.insert(0, str(_alldom_path.parent))
    from alldom.bridges.whois import (
        lookup as alldom_whois_lookup,
        history as alldom_whois_history,
        reverse as alldom_whois_reverse,
        cluster as alldom_whois_cluster,
        entities as alldom_whois_entities,
        fetch_current_whois_record,
        WhoisRecord,
    )
    ALLDOM_WHOIS_AVAILABLE = True
    logger.info("ALLDOM WHOIS bridge loaded")
except ImportError as _alldom_err:
    logger.debug(f"ALLDOM WHOIS bridge not available: {_alldom_err}")
    alldom_whois_lookup = None
    alldom_whois_history = None
    alldom_whois_reverse = None
    alldom_whois_cluster = None
    alldom_whois_entities = None
    fetch_current_whois_record = None
    WhoisRecord = None
    ALLDOM_WHOIS_AVAILABLE = False


# Output Mapper - Maps module results to I/O Matrix field codes
try:
    from output_mapper import OutputMapper, get_mapper, FIELD_CODES
    OUTPUT_MAPPER_AVAILABLE = True
    logger.info("Output mapper loaded")
except ImportError as _mapper_err:
    logger.debug(f"Output mapper not available: {_mapper_err}")
    OutputMapper = None
    get_mapper = None
    FIELD_CODES = {}
    OUTPUT_MAPPER_AVAILABLE = False


# =============================================================================
# MACRO I/O LOGGING - Tracks all macro executions with input/output
# =============================================================================

class MacroLogger:
    """
    Logs macro executions with structured input/output tracking.

    Each macro execution is logged with:
    - timestamp
    - macro_name (e.g., 'alldom', 'related_company', 'company_website')
    - input_code (IO Matrix field code, e.g., 6 = domain, 13 = company_name)
    - input_value
    - output_codes (list of output field codes)
    - duration_seconds
    - status (success/error)

    Logs are stored as JSONL in IO_LOGS_DIR/macro_io.jsonl
    """

    LOG_FILE = IO_LOGS_DIR / "macro_io.jsonl"

    # Macro I/O field codes (from codes.json)
    # These map macro names to their input/output codes
    MACRO_IO_CODES = {
        'company_website': {'input': 13, 'outputs': [6]},                    # company_name → domain_url
        'age': {'input': 7, 'outputs': [12, 502]},                           # person_name → person_dob, person_age
        'alldom': {'input': 6, 'outputs': [503, 504, 505, 506, 507, 508]},   # domain → alldom_full_profile, etc.
        'related_company': {'input': 13, 'outputs': [500, 501]},             # company_name → related_companies, evidence
        'reputation_analytics': {'input': 13, 'outputs': [510, 511, 512, 513, 514, 515]},  # entity → news, social, trust/citation flow, reputation
    }

    @classmethod
    def log_execution(cls, macro_name: str, input_value: str, result: Dict[str, Any],
                      duration_seconds: float, success: bool = True, error: str = None):
        """
        Log a macro execution.

        Args:
            macro_name: Name of the macro (e.g., 'alldom')
            input_value: The input value passed to the macro
            result: The output result dict from the macro
            duration_seconds: Execution time
            success: Whether execution succeeded
            error: Error message if failed
        """
        io_codes = cls.MACRO_IO_CODES.get(macro_name, {'input': 0, 'outputs': []})

        log_entry = {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'macro_name': macro_name,
            'input_code': io_codes['input'],
            'input_value': input_value,
            'output_codes': io_codes['outputs'],
            'output_count': len(result.get('related', [])) if 'related' in result else 1,
            'duration_seconds': round(duration_seconds, 3),
            'success': success,
            'error': error,
        }

        # Append to JSONL log file
        try:
            with open(cls.LOG_FILE, 'a') as f:
                f.write(json.dumps(log_entry) + '\n')
        except Exception as e:
            logger.warning(f"Failed to log macro execution: {e}")

    @classmethod
    def get_recent_logs(cls, limit: int = 100) -> List[Dict]:
        """Get recent macro execution logs."""
        if not cls.LOG_FILE.exists():
            return []

        logs = []
        try:
            with open(cls.LOG_FILE) as f:
                for line in f:
                    if line.strip():
                        logs.append(json.loads(line))
        except Exception as e:
            logger.warning(f"Failed to read macro logs: {e}")
            return []

        return logs[-limit:]


class MacroExecutor:
    """
    Executes macros from the /macros directory.

    Macros are Python packages with a main() entry point.
    Each macro is invoked via subprocess for isolation.

    Usage:
        executor = MacroExecutor()
        result = await executor.execute('alldom', 'example.com')
        result = await executor.execute('related_company', 'Acme Corp', jurisdiction='GB', domain='acme.com')
    """

    # Available macros and their operators
    MACRO_OPERATORS = {
        'cdom': 'company_website',      # cdom? → Find company website/domain
        'age': 'age',                   # age? → Find person age/DOB
        'alldom': 'alldom',             # alldom? → Full domain analysis
        'crel': 'related_company',      # crel? → Find related companies
        'rep': 'reputation_analytics',  # rep? → Reputation analytics
    }

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self._available_macros = self._discover_macros()

    def _discover_macros(self) -> Dict[str, Path]:
        """Discover available macros in MACROS_DIR."""
        macros = {}
        if MACROS_DIR.exists():
            for item in MACROS_DIR.iterdir():
                if item.is_dir() and (item / '__init__.py').exists():
                    macros[item.name] = item
        return macros

    @property
    def available_macros(self) -> List[str]:
        """List of available macro names."""
        return list(self._available_macros.keys())

    async def execute(self, macro_name: str, value: str, **kwargs) -> Dict[str, Any]:
        """
        Execute a macro and return its result.

        Args:
            macro_name: Name of the macro (e.g., 'alldom', 'related_company')
            value: Primary input value
            **kwargs: Additional arguments (jurisdiction, domain, etc.)

        Returns:
            Dict with macro result or error
        """
        if macro_name not in self._available_macros:
            return {'error': f'Macro not found: {macro_name}', 'available': self.available_macros}

        if self.dry_run:
            return {
                'macro': macro_name,
                'value': value,
                'kwargs': kwargs,
                'status': 'dry_run',
                'would_execute': True,
                'macro_path': str(self._available_macros[macro_name]),
            }

        start_time = datetime.utcnow()

        # Build command
        cmd = [sys.executable, '-m', f'macros.{macro_name}', value, '--json']

        # Add optional arguments
        if kwargs.get('jurisdiction'):
            cmd.extend(['--jurisdiction', kwargs['jurisdiction']])
        if kwargs.get('domain'):
            cmd.extend(['--domain', kwargs['domain']])
        if kwargs.get('address'):
            cmd.extend(['--address', kwargs['address']])
        if kwargs.get('number'):
            cmd.extend(['--number', kwargs['number']])

        # Set PYTHONPATH to include macros parent directory
        env = os.environ.copy()
        macros_parent = str(MACROS_DIR.parent)
        if 'PYTHONPATH' in env:
            env['PYTHONPATH'] = f"{macros_parent}:{env['PYTHONPATH']}"
        else:
            env['PYTHONPATH'] = macros_parent

        try:
            # Run macro as subprocess
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=str(MACROS_DIR.parent),
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=300  # 5 minute timeout
            )

            duration = (datetime.utcnow() - start_time).total_seconds()

            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else f'Exit code {process.returncode}'
                MacroLogger.log_execution(
                    macro_name, value, {}, duration, success=False, error=error_msg
                )
                return {
                    'error': f'Macro execution failed: {error_msg}',
                    'macro': macro_name,
                    'exit_code': process.returncode,
                }

            # Parse JSON output
            try:
                result = json.loads(stdout.decode())
            except json.JSONDecodeError:
                result = {'raw_output': stdout.decode(), 'macro': macro_name}

            result['duration_seconds'] = duration
            result['macro'] = macro_name

            # Log successful execution
            MacroLogger.log_execution(macro_name, value, result, duration, success=True)

            return result

        except asyncio.TimeoutError:
            duration = (datetime.utcnow() - start_time).total_seconds()
            MacroLogger.log_execution(macro_name, value, {}, duration, success=False, error='Timeout')
            return {'error': 'Macro execution timed out', 'macro': macro_name, 'timeout': 300}
        except Exception as e:
            duration = (datetime.utcnow() - start_time).total_seconds()
            MacroLogger.log_execution(macro_name, value, {}, duration, success=False, error=str(e))
            return {'error': f'Macro execution error: {str(e)}', 'macro': macro_name}

    def parse_macro_operator(self, query: str) -> Optional[Tuple[str, str]]:
        """
        Parse a macro operator query.

        Supports patterns like:
        - cdom? company name
        - alldom? example.com
        - crel? Acme Corp

        Returns:
            Tuple of (macro_name, value) or None if not a macro query
        """
        for operator, macro_name in self.MACRO_OPERATORS.items():
            # Pattern: operator? value or operator: value
            patterns = [
                rf'^{operator}\?\s*(.+)',
                rf'^{operator}:\s*(.+)',
            ]
            for pattern in patterns:
                match = re.match(pattern, query, re.IGNORECASE)
                if match:
                    return macro_name, match.group(1).strip()
        return None


class RealityEngineAdapter:
    """Adapts IO CLI results into Reality Engine (nodes/edges) format."""

    def __init__(self, io_results: Dict[str, Any]):
        self.raw_results = io_results
        self.nodes = {}
        self.edges = []
        self._convert()

    def _convert(self):
        """Convert IO results to graph state."""
        # Create root node (the subject of investigation)
        root_type = self.raw_results.get("entity_type", "unknown")
        root_value = self.raw_results.get("value", "unknown")
        root_id = f"root_{root_value.replace(' ', '_')}"
        
        self.nodes[root_id] = self._make_node(root_id, "subject", root_type, root_value)

        # Naive extraction from 'results' dict
        # This is a basic mapping for demonstration. In production, Jester handles this.
        results = self.raw_results.get("results", {})
        
        # Example: Extract from WDC results
        wdc_entities = results.get("schema_org_entities", [])
        if isinstance(wdc_entities, list):
            for i, entity in enumerate(wdc_entities):
                e_id = f"wdc_{i}"
                label = entity.get("name") or "Unknown"
                self.nodes[e_id] = self._make_node(e_id, "subject", "entity", label)
                
                # Link to root
                self.edges.append(self._make_edge(root_id, e_id, "related_to"))

        # Example: Extract Transactions (if any) to test Event Physics
        # If we found a "transaction" or "payment" in text, we'd model it here.
        # For the integration test, we will inject a partial event if 'test_event_mode' is active.
        if self.raw_results.get("test_event_mode"):
            evt_id = "evt_simulated"
            self.nodes[evt_id] = self._make_node(evt_id, "event", "TRANSACTION_VALUE_TRANSFER", "Simulated Transfer")
            # Link root as originator
            self.edges.append(self._make_edge(root_id, evt_id, "originated"))
            # Missing beneficiary -> Hunger

    def _make_node(self, id, class_, type_, label):
        # Dynamic object to match what Assessor expects (getattr access)
        class Node:
            def __init__(self, i, c, t, l):
                self.id = i
                self.class_ = c # Mapped to 'class' via property if needed, or Assessor updated
                self.type = t
                self.label = l
                self.properties = {}
            @property
            def _class(self): return self.class_ # Fallback
            
        n = Node(id, class_, type_, label)
        # Monkey patch class attribute access for the Assessor which might use getattr(n, "class")
        # Python 'class' is reserved, so we use this trick if Assessor uses it.
        # However, Assessor.py uses getattr(n, "class", "") which works on instances if we setattr
        setattr(n, "class", class_) 
        return n

    def _make_edge(self, src, tgt, rel):
        class Edge:
            def __init__(self, s, t, r):
                self.source = s
                self.target = t
                self.relationship = r
        return Edge(src, tgt, rel)


# =============================================================================
# PREFIX PARSER - Parse prefix operators (p:, c:, e:, t:, d:)
# =============================================================================

def parse_prefix(query: str) -> Tuple[Optional[str], str, Optional[str]]:
    """Parse prefix operator from query, supporting qualified operators.

    Returns: (entity_type, value, jurisdiction)

    Examples:
        "p: John Smith"    -> ("person", "John Smith", None)
        "pde: John Smith"  -> ("person", "John Smith", "DE")
        "chr: Podravka"    -> ("company", "Podravka", "HR")
        "cnl: Acme BV"     -> ("company", "Acme BV", "NL")
        "lituk: Acme Ltd"  -> ("litigation", "Acme Ltd", "UK")
        "crua: Test LLC"   -> ("corporate_registry", "Test LLC", "UA")
    """
    query_lower = query.strip()

    # Social media prefixes (pass through to social_media handler)
    social_match = re.match(
        r'^(fb|facebook|tw|twitter|x|ig|instagram|threads|social|all)\s*:\s*(.*)$',
        query_lower,
        re.IGNORECASE,
    )
    if social_match:
        prefix = social_match.group(1).lower()
        value = social_match.group(2).strip()
        if not value:
            return "social_media", None, None
        return "social_media", f"{prefix}: {value}".strip(), None

    # Match prefix: anything before colon
    colon_match = re.match(r'^([a-z]{1,10}):\s*(.*)$', query_lower, re.IGNORECASE)
    if not colon_match:
        return None, query, None

    full_prefix = colon_match.group(1).lower()
    value = colon_match.group(2).strip()

    # Known entity type/intent codes
    type_map = {
        'p': 'person',
        'c': 'company',
        'e': 'email',
        't': 'phone',
        'd': 'domain',
        'dom': 'domain',
        'u': 'username',
        'li': 'linkedin_url',
        'linkedin': 'linkedin_url',
        'liu': 'linkedin_username',
        'liuser': 'linkedin_username',
        'b': 'brand', 'pr': 'product', 'lit': 'litigation', 'cr': 'corporate_registry',
        'prop': 'property', 'san': 'sanctions', 'pep': 'pep', 'off': 'officers', 'own': 'ownership',
        'news': 'news', 'n': 'news',
        # UK-specific operators
        'reg': 'regulatory', 'foi': 'foi'
    }

    # UK-SPECIFIC OPERATORS - Route directly to UK unified module
    # Format: {operator_prefix: (entity_type, jurisdiction)}
    uk_operators = {
        'cuk': ('company', 'UK'),
        'puk': ('person', 'UK'),
        'reguk': ('regulatory', 'UK'),
        'lituk': ('litigation', 'UK'),
        'cruk': ('corporate_registry', 'UK'),
        'assuk': ('assets', 'UK'),
        'foiuk': ('foi', 'UK'),
        'docuk': ('document_extraction', 'UK'),  # PDF download + Claude OCR extraction
    }

    # Check for UK-specific operators first
    for uk_op, (etype, jur) in uk_operators.items():
        if full_prefix == uk_op:
            return etype, value, jur

    # Try to match longest prefix first, then extract jurisdiction suffix
    jurisdiction = None
    entity_type = None

    # Case 1: Type(1-4) + Jur(2) (e.g., pde:, lituk:)
    for prefix, etype in sorted(type_map.items(), key=lambda x: -len(x[0])):
        if full_prefix.startswith(prefix):
            remaining = full_prefix[len(prefix):]
            if len(remaining) == 4 and remaining.startswith("us"):
                entity_type = etype
                jurisdiction = f"US_{remaining[2:].upper()}"
                break
            if len(remaining) == 2:
                entity_type = etype
                jurisdiction = remaining.upper()
                break
            elif not remaining:
                entity_type = etype
                break

    # Case 2: Jur(2) + Type(1-4) (e.g., atcr:, huoff:)
    if not jurisdiction and len(full_prefix) >= 3:
        potential_jur = full_prefix[:2].upper()
        potential_type = full_prefix[2:]
        if potential_type in type_map:
            entity_type = type_map[potential_type]
            jurisdiction = potential_jur

    # Fallback to simple prefix
    if entity_type is None:
        entity_type = full_prefix

    if entity_type == "linkedin_url" and value:
        value = normalize_linkedin_url(value)
    elif entity_type == "linkedin_username" and value:
        value = normalize_linkedin_username(value)

    return entity_type, value, jurisdiction


# =============================================================================
# LINKLATER OPERATOR DETECTION/EXECUTION
# =============================================================================

_LINKLATER_OPERATOR_RE = re.compile(
    r'(^|\s)(\?bl|bl\?|\?ol|ol\?|ent\?|p\?|c\?|t\?|e\?|a\?|pdf!|doc!|word!|xls!|ppt!|file!|=\?|'
    r'\?scrape)(\s|:|$)',
    re.IGNORECASE
)
_LINKLATER_TARGET_ONLY_RE = re.compile(
    r'^\s*(<-\d{4}!|<-!|\d{4}!|\d{4}-\d{4}!)?\s*!\S+',
    re.IGNORECASE
)


def _try_parse_linklater(query: str):
    if not LINKLATER_PARSER_AVAILABLE:
        return None
    try:
        return parse_linklater_query(query)
    except Exception:
        return None


def _looks_like_linklater_query(query: str, parsed=None) -> bool:
    if parsed is not None:
        return True
    q = query.strip()
    if not q:
        return False
    if q.endswith(" :tor") or q.endswith(" :onion") or q.endswith(":tor") or q.endswith(":onion"):
        return True
    if _LINKLATER_OPERATOR_RE.search(q):
        return True
    if _LINKLATER_TARGET_ONLY_RE.match(q):
        return True
    return False


def _linklater_dry_run_summary(query: str, parsed) -> Dict[str, Any]:
    if not parsed:
        return {"error": f"Invalid LINKLATER query: {query}"}
    return {
        "mode": "linklater_operator",
        "query": query,
        "target": parsed.target,
        "target_type": parsed.target_type.value,
        "historical": str(parsed.historical),
        "tor_context": parsed.tor_context,
        "operators": [op.value for op in parsed.operators],
        "entity_types": sorted(parsed.entity_types),
        "filetype_types": sorted(parsed.filetype_types),
        "wants_backlinks": parsed.wants_backlinks,
        "wants_outlinks": parsed.wants_outlinks,
        "wants_entities": parsed.wants_entities
    }


def _run_linklater_query(query: str, parsed=None, dry_run: bool = False) -> Dict[str, Any]:
    if dry_run:
        return _linklater_dry_run_summary(query, parsed)

    if not LINKLATER_EXECUTOR_AVAILABLE:
        return {"error": "LINKLATER executor unavailable (missing dependencies or import failure)."}

    executor = LinklaterQueryExecutor()

    async def _execute():
        try:
            return await executor.execute_async(query)
        finally:
            try:
                if hasattr(executor, "historical_fetcher") and executor.historical_fetcher:
                    await executor.historical_fetcher.close()
            except Exception:
                pass

    try:
        return asyncio.run(_execute())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(_execute())


def _is_domainish(value: str) -> bool:
    if not value:
        return False
    return "." in value or "/" in value


def _linklater_root_value(query: str, parsed=None) -> str:
    if parsed and parsed.tor_context and (not parsed.target or parsed.target == "*"):
        return "tor_index"
    if parsed and parsed.target:
        return parsed.target
    return query


def _linklater_root_type(root_value: str, parsed=None) -> str:
    if parsed and getattr(parsed, "target_type", None):
        target_type = parsed.target_type.value
        if target_type in ("domain", "page") and _is_domainish(root_value):
            return "domain"
    if _is_domainish(root_value):
        return "domain"
    return "keyword"


def _normalize_linklater_items(items, default_type: Optional[str] = None) -> List[Dict[str, Any]]:
    normalized = []
    if not isinstance(items, list):
        return normalized
    for item in items:
        if isinstance(item, dict):
            name = item.get("name") or item.get("title") or item.get("url") or item.get("domain")
            normalized_item = dict(item)
            if name:
                normalized_item.setdefault("name", str(name))
            if default_type and "type" not in normalized_item:
                normalized_item["type"] = default_type
            normalized.append(normalized_item)
        else:
            normalized.append({"name": str(item), "type": default_type or "value"})
    return normalized


def _normalize_linklater_backlinks(items) -> List[Dict[str, Any]]:
    normalized = []
    if not isinstance(items, list):
        return normalized
    for item in items:
        if not isinstance(item, dict):
            normalized.append({"name": str(item), "type": "backlink"})
            continue
        if item.get("domain") and not item.get("url"):
            name = item.get("domain")
            item_type = "domain"
        else:
            name = item.get("url") or item.get("domain")
            item_type = "url"
        normalized_item = dict(item)
        if name:
            normalized_item.setdefault("name", str(name))
        normalized_item.setdefault("type", item_type)
        normalized.append(normalized_item)
    return normalized


def _normalize_linklater_outlinks(items) -> List[Dict[str, Any]]:
    normalized = []
    if not isinstance(items, list):
        return normalized
    for item in items:
        if not isinstance(item, dict):
            normalized.append({"name": str(item), "type": "outlink"})
            continue
        if item.get("domain") and not item.get("url"):
            name = item.get("domain")
            item_type = "domain"
        else:
            name = item.get("url") or item.get("domain")
            item_type = "url"
        normalized_item = dict(item)
        if name:
            normalized_item.setdefault("name", str(name))
        normalized_item.setdefault("type", item_type)
        normalized.append(normalized_item)
    return normalized


def _normalize_linklater_files(items) -> List[Dict[str, Any]]:
    normalized = []
    if not isinstance(items, list):
        return normalized
    for item in items:
        if not isinstance(item, dict):
            normalized.append({"name": str(item), "type": "file"})
            continue
        filetype = item.get("filetype")
        title = item.get("title") or item.get("url") or ""
        if filetype and title:
            name = f"{filetype.upper()}: {title}"
        else:
            name = title or filetype or "file"
        normalized_item = dict(item)
        normalized_item.setdefault("name", str(name))
        normalized_item.setdefault("type", filetype or "file")
        normalized.append(normalized_item)
    return normalized


def _flatten_linklater_entities(entities) -> List[Dict[str, Any]]:
    flattened = []
    if isinstance(entities, dict):
        for ent_key, ent_list in entities.items():
            ent_key_str = ent_key if isinstance(ent_key, str) else "entity"
            ent_type = ent_key_str.rstrip("s")
            if not isinstance(ent_list, list):
                continue
            for ent in ent_list:
                if isinstance(ent, dict):
                    name = ent.get("name") or ent.get("value") or ent.get("label") or ent.get("title")
                    item_type = ent.get("type") or ent_type
                    normalized = dict(ent)
                    if name:
                        normalized.setdefault("name", str(name))
                    normalized.setdefault("type", item_type)
                    flattened.append(normalized)
                else:
                    flattened.append({"name": str(ent), "type": ent_type})
    elif isinstance(entities, list):
        for ent in entities:
            if isinstance(ent, dict):
                name = ent.get("name") or ent.get("value") or ent.get("label") or ent.get("title")
                normalized = dict(ent)
                if name:
                    normalized.setdefault("name", str(name))
                flattened.append(normalized)
            else:
                flattened.append({"name": str(ent), "type": "entity"})
    return flattened


def _normalize_linklater_snapshots(items) -> List[Dict[str, Any]]:
    normalized = []
    if not isinstance(items, list):
        return normalized
    for item in items:
        if not isinstance(item, dict):
            normalized.append({"name": str(item), "type": "snapshot"})
            continue
        timestamp = item.get("timestamp") or item.get("year")
        url = item.get("url") or item.get("original") or ""
        if timestamp and url:
            name = f"{timestamp}: {url}"
        else:
            name = url or str(timestamp) if timestamp is not None else "snapshot"
        normalized_item = dict(item)
        normalized_item.setdefault("name", str(name))
        normalized_item.setdefault("type", "snapshot")
        normalized.append(normalized_item)
    return normalized


def _linklater_results_for_viz(query: str, result: Dict[str, Any], parsed=None) -> Dict[str, Any]:
    parsed = parsed or _try_parse_linklater(query)
    root_value = _linklater_root_value(query, parsed)
    entity_type = _linklater_root_type(root_value, parsed)

    results = {}
    payload = result.get("results", {}) if isinstance(result, dict) else {}

    backlinks = payload.get("backlinks")
    outlinks = payload.get("outlinks")
    entities = payload.get("entities")
    files = payload.get("files")
    onion_urls = payload.get("onion_urls")
    onion_pages = payload.get("onion_pages")

    if backlinks:
        results["linklater_backlinks"] = _normalize_linklater_backlinks(backlinks)
    if outlinks:
        results["linklater_outlinks"] = _normalize_linklater_outlinks(outlinks)
    if entities:
        results["linklater_entities"] = _flatten_linklater_entities(entities)
    if files:
        results["linklater_files"] = _normalize_linklater_files(files)
    if onion_urls:
        results["linklater_onion_urls"] = _normalize_linklater_items(onion_urls, default_type="url")
    if onion_pages:
        results["linklater_onion_pages"] = _normalize_linklater_items(onion_pages, default_type="page")

    snapshots = result.get("snapshots")
    if snapshots:
        results["linklater_snapshots"] = _normalize_linklater_snapshots(snapshots)

    if not results and isinstance(result, dict) and result.get("error"):
        results["linklater_error"] = {"error": result.get("error")}

    return {
        "entity_type": entity_type,
        "value": root_value,
        "results": results,
    }


# =============================================================================
# MATRIX QUERY PARSER - Parse exploration queries ([?]=>TYPE, TYPE=>[?])
# =============================================================================

def parse_matrix_query(query: str) -> Optional[Dict[str, Any]]:
    """Parse matrix exploration queries.

    Syntax:
        [?]=>TYPE    - What inputs produce this output? (reverse lookup)
        TYPE=>[?]    - What outputs from this input? (forward lookup)
        TYPE=>TYPE   - Route between two types

    Type format:
        e, email     - Email
        c, company   - Company
        chu          - Company + HU jurisdiction
        chuid        - Company ID + HU jurisdiction
        pid          - Person ID (all types)

    Returns dict with:
        mode: 'reverse' | 'forward' | 'route'
        input_type: str or None
        output_type: str or None
        input_jurisdiction: str or None
        output_jurisdiction: str or None
    """
    query = query.strip()

    # Pattern: [?]=>TYPE or ?=>TYPE (reverse lookup)
    reverse_match = re.match(r'^\[?\?\]?\s*=>\s*(.+)$', query)
    if reverse_match:
        output_spec = reverse_match.group(1)
        output_type, output_jur = _parse_type_spec(output_spec)
        return {
            'mode': 'reverse',
            'input_type': None,
            'output_type': output_type,
            'input_jurisdiction': None,
            'output_jurisdiction': output_jur
        }

    # Pattern: TYPE=>[?] or TYPE=>? (forward lookup)
    forward_match = re.match(r'^(.+?)\s*=>\s*\[?\?\]?(.*)$', query)
    if forward_match:
        input_spec = forward_match.group(1)
        output_filter = forward_match.group(2).strip()  # Optional jurisdiction filter
        input_type, input_jur = _parse_type_spec(input_spec)
        output_jur = None
        if output_filter:
            # Handle [?hu] -> extract 'hu'
            jur_match = re.match(r'^\[?([a-z]{2})\]?$', output_filter, re.IGNORECASE)
            if jur_match:
                output_jur = jur_match.group(1).upper()
        return {
            'mode': 'forward',
            'input_type': input_type,
            'output_type': None,
            'input_jurisdiction': input_jur,
            'output_jurisdiction': output_jur
        }

    # Pattern: TYPE=>TYPE (route lookup)
    route_match = re.match(r'^(.+?)\s*=>\s*(.+)$', query)
    if route_match and '=>' in query and '[?' not in query and '?]' not in query:
        input_spec = route_match.group(1)
        output_spec = route_match.group(2)
        input_type, input_jur = _parse_type_spec(input_spec)
        output_type, output_jur = _parse_type_spec(output_spec)
        return {
            'mode': 'route',
            'input_type': input_type,
            'output_type': output_type,
            'input_jurisdiction': input_jur,
            'output_jurisdiction': output_jur
        }

    return None


def _parse_type_spec(spec: str) -> Tuple[str, Optional[str]]:
    """Parse type specification like 'chu', 'chuid', 'email', 'pde'.

    Returns: (canonical_type, jurisdiction)
    """
    spec = spec.strip().lower()

    # Type aliases
    type_map = {
        'e': 'email',
        'p': 'person',
        'c': 'company',
        't': 'phone',
        'dom': 'domain',
        'u': 'username',
        'li': 'linkedin_url',
        'cid': 'company_reg_id',
        'pid': 'person_id',
        'eid': 'email',  # email is its own ID
        'domid': 'domain',
    }

    # Check for embedded jurisdiction (last 2 chars if length > 2)
    jurisdiction = None
    base_type = spec

    if len(spec) > 2:
        # Check if ends with 2-letter jurisdiction
        potential_jur = spec[-2:]
        potential_base = spec[:-2]

        # Known type prefixes
        if potential_base in type_map or potential_base in ['company', 'person', 'email', 'phone', 'domain', 'username']:
            jurisdiction = potential_jur.upper()
            base_type = potential_base

    # Resolve alias
    canonical = type_map.get(base_type, base_type)

    return canonical, jurisdiction


class MatrixExplorer:
    """Explore the IO Matrix - discover routes, sources, and capabilities.

    Answers questions like:
    - [?]=>email: What sources can give me email output?
    - company=>[?]: What can I get from a company name?
    - chu=>[?]: What can I get from a Hungarian company?
    """

    FLOWS_PATH = Path(__file__).parent / "flows.json"
    IO_INTEGRATION_PATH = resolve_io_integration_path()
    CODES_PATH = Path(__file__).parent / "codes.json"

    # Comprehensive input type aliases for normalization
    INPUT_ALIASES = {
        # Entity types
        'company': 'company_name',
        'person': 'person_name',
        'email': 'email',
        'email_address': 'email',
        'phone': 'phone',
        'phone_number': 'phone',
        'domain': 'domain_url',
        'domain_name': 'domain_url',
        'username': 'username',
        'address': 'property_address',
        # ID types
        'company_id': 'company_reg_id',
        'company_number': 'company_reg_id',
        'registration_number': 'company_reg_id',
        'reg_id': 'company_reg_id',
        'person_id': 'person_national_id',
        'national_id': 'person_national_id',
        'tax_id': 'company_vat_id',
        'vat': 'company_vat_id',
        'vat_id': 'company_vat_id',
        # Common variations
        'ticker': 'company_ticker',
        'ticker_symbol': 'company_ticker',
        'linkedin': 'person_linkedin_url',
        'linkedin_url': 'person_linkedin_url',
        'website': 'domain_url',
        'url': 'domain_url',
    }

    def __init__(self):
        self.flows = self._load_json(self.FLOWS_PATH)
        self.io_config = self._load_json(self.IO_INTEGRATION_PATH)
        self._load_codes()
        self._build_indices()

    def _load_json(self, path: Path) -> Dict:
        if path.exists():
            with open(path) as f:
                return json.load(f)
        return {}

    def _load_codes(self):
        """Load codes.json and build legend (code -> name mapping)."""
        codes_data = self._load_json(self.CODES_PATH)
        codes_section = codes_data.get('codes', {})

        # Build legend: code -> name
        self.legend = {}
        for code, info in codes_section.items():
            if isinstance(info, dict) and 'name' in info:
                self.legend[code] = info['name']

    def _build_indices(self):
        """Build lookup indices for fast queries."""
        # name -> code mapping
        self.name_to_code = {}
        for code, name in self.legend.items():
            self.name_to_code[name] = int(code)
            # Also add without underscores
            self.name_to_code[name.replace('_', '')] = int(code)

        # Add all input aliases
        for alias, canonical in self.INPUT_ALIASES.items():
            if canonical in self.name_to_code:
                self.name_to_code[alias] = self.name_to_code[canonical]

        # Forward index: input_type -> list of (output_types, route_info)
        self.forward_routes = defaultdict(list)
        # Reverse index: output_type -> list of (input_type, route_info)
        self.reverse_routes = defaultdict(list)
        # String-based indices for types without codes
        self.forward_routes_str = defaultdict(list)
        self.reverse_routes_str = defaultdict(list)
        # All routes flat list
        self.all_routes = []

        # flows.json is organized as {"flows": {country_code: [routes...]}}
        flows_data = self.flows.get('flows', self.flows)
        for country_code, routes in flows_data.items():
            if not isinstance(routes, list):
                continue
            for route in routes:
                input_type = route.get('input_type', '')
                output_columns = route.get('output_columns_array', [])

                if not input_type or not output_columns:
                    continue

                # Normalize input_type using aliases
                input_normalized = self._normalize_type(input_type)
                input_code = self.name_to_code.get(input_normalized) or self.name_to_code.get(input_type)

                route_info = {
                    'source': route.get('source_label', route.get('source_id', 'unknown')),
                    'jurisdiction': country_code,
                    'kind': route.get('kind'),
                    'reliability': route.get('reliability'),
                    'description': route.get('notes', ''),
                    'input_type': input_type,
                    'output_types': output_columns
                }
                self.all_routes.append(route_info)

                # Build forward index (input -> outputs)
                for output_col in output_columns:
                    output_normalized = self._normalize_type(output_col)
                    output_code = self.name_to_code.get(output_normalized) or self.name_to_code.get(output_col)

                    # Code-based indexing (preferred)
                    if input_code and output_code:
                        self.forward_routes[input_code].append({
                            'output': output_code,
                            'output_name': output_col,
                            'route': route_info
                        })
                        self.reverse_routes[output_code].append({
                            'input': input_code,
                            'input_name': input_type,
                            'route': route_info
                        })

                    # String-based indexing (fallback for types without codes)
                    self.forward_routes_str[input_normalized].append({
                        'output': output_col,
                        'route': route_info
                    })
                    self.reverse_routes_str[output_normalized].append({
                        'input': input_type,
                        'route': route_info
                    })

    def _normalize_type(self, type_name: str) -> str:
        """Normalize a type name using aliases and common patterns."""
        if not type_name:
            return type_name

        # Check direct alias
        if type_name in self.INPUT_ALIASES:
            return self.INPUT_ALIASES[type_name]

        # Common suffix normalization
        normalized = type_name
        normalized = normalized.replace('_address', '')
        normalized = normalized.replace('_number', '')

        # Check alias for normalized version
        if normalized in self.INPUT_ALIASES:
            return self.INPUT_ALIASES[normalized]

        return type_name

    # Type aliases for common lookups (legacy compatibility)
    TYPE_ALIASES = {
        'company': 'company_name',
        'person': 'person_name',
        'email': 'email',
        'phone': 'phone',
        'domain': 'domain_url',
        'username': 'username',
        'address': 'property_address',
        'company_id': 'company_reg_id',
        'person_id': 'person_national_id',
    }

    def get_code_for_type(self, type_name: str) -> Optional[int]:
        """Get field code for a type name."""
        # Check alias first
        canonical = self.TYPE_ALIASES.get(type_name, type_name)

        # Direct lookup
        if canonical in self.name_to_code:
            return self.name_to_code[canonical]
        # Try with common prefixes
        for prefix in ['', 'company_', 'person_', 'domain_']:
            full_name = prefix + canonical
            if full_name in self.name_to_code:
                return self.name_to_code[full_name]
        return None

    def explore(self, query: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a matrix exploration query."""
        mode = query['mode']

        if mode == 'reverse':
            return self._reverse_lookup(query)
        elif mode == 'forward':
            return self._forward_lookup(query)
        elif mode == 'route':
            return self._route_lookup(query)

        return {'error': f'Unknown mode: {mode}'}

    def _reverse_lookup(self, query: Dict) -> Dict:
        """What inputs can produce this output?"""
        output_type = query['output_type']
        output_jur = query.get('output_jurisdiction')

        output_code = self.get_code_for_type(output_type)
        output_name = self.legend.get(str(output_code), output_type) if output_code else output_type
        output_normalized = self._normalize_type(output_type)

        result = {
            'query': f'[?]=>{output_type}' + (output_jur or ''),
            'question': f'What can produce {output_name}?',
            'output_type': output_name,
            'output_code': output_code,
            'jurisdiction_filter': output_jur,
            'sources': [],
            'routes': []
        }

        seen_routes = set()  # Dedupe by (input, source, jurisdiction)

        # Code-based lookup (preferred)
        if output_code:
            for route_info in self.reverse_routes.get(output_code, []):
                input_code = route_info['input']
                input_name = self.legend.get(str(input_code), f'code_{input_code}')
                route = route_info['route']

                # Filter by jurisdiction if specified
                if output_jur and route.get('jurisdiction'):
                    if route['jurisdiction'].upper() != output_jur.upper():
                        continue

                route_key = (input_name, route.get('source'), route.get('jurisdiction'))
                if route_key in seen_routes:
                    continue
                seen_routes.add(route_key)

                result['routes'].append({
                    'input_type': input_name,
                    'input_code': input_code,
                    'source': route.get('source', 'unknown'),
                    'jurisdiction': route.get('jurisdiction'),
                    'method': route.get('method'),
                    'description': route.get('description', '')
                })

        # String-based fallback lookup
        for route_info in self.reverse_routes_str.get(output_normalized, []):
            route = route_info['route']
            input_type = route_info['input']

            # Filter by jurisdiction if specified
            if output_jur and route.get('jurisdiction'):
                if route['jurisdiction'].upper() != output_jur.upper():
                    continue

            route_key = (input_type, route.get('source'), route.get('jurisdiction'))
            if route_key in seen_routes:
                continue
            seen_routes.add(route_key)

            result['routes'].append({
                'input_type': input_type,
                'input_code': self.name_to_code.get(input_type),
                'source': route.get('source', 'unknown'),
                'jurisdiction': route.get('jurisdiction'),
                'method': route.get('method'),
                'description': route.get('description', '')
            })

        # Also find ES indices that have this field
        for idx_name, idx_info in self.io_config.get('index_metadata', {}).items():
            output_fields = idx_info.get('output_fields', [])
            if output_code and output_code in output_fields:
                result['sources'].append({
                    'type': 'elasticsearch',
                    'index': idx_name,
                    'cluster': idx_info.get('cluster'),
                    'description': idx_info.get('description', '')
                })

        # Find modules that output this type
        for mod_type, mod_configs in self.io_config.get('module_executors', {}).items():
            for mod in mod_configs:
                outputs = mod.get('outputs', [])
                if output_type in outputs or output_normalized in outputs or (output_code and output_code in outputs):
                    result['sources'].append({
                        'type': 'module',
                        'module': mod.get('module'),
                        'method': mod.get('method') or mod.get('function'),
                        'input_type': mod_type
                    })

        return result

    def _forward_lookup(self, query: Dict) -> Dict:
        """What outputs can I get from this input?"""
        input_type = query['input_type']
        input_jur = query.get('input_jurisdiction')
        output_jur = query.get('output_jurisdiction')

        input_code = self.get_code_for_type(input_type)
        input_name = self.legend.get(str(input_code), input_type) if input_code else input_type
        input_normalized = self._normalize_type(input_type)

        jur_str = input_jur or ''
        output_filter_str = f'[{output_jur.lower()}]' if output_jur else ''

        question = f'What can I get from {input_name}'
        if input_jur:
            question += f' ({input_jur})'
        if output_jur:
            question += f' from {output_jur} sources'
        question += '?'

        result = {
            'query': f'{input_type}{jur_str}=>[?]{output_filter_str}',
            'question': question,
            'input_type': input_name,
            'input_code': input_code,
            'jurisdiction': input_jur,
            'output_filter': output_jur,
            'outputs': [],
            'sources': []
        }

        seen_outputs = set()  # Dedupe by (output, source, jurisdiction)

        # Code-based lookup (preferred)
        if input_code:
            for route_info in self.forward_routes.get(input_code, []):
                output_code = route_info['output']
                output_name = self.legend.get(str(output_code), f'code_{output_code}')
                route = route_info['route']

                # Filter by input jurisdiction (route must be from this jurisdiction)
                if input_jur and route.get('jurisdiction'):
                    if route['jurisdiction'].upper() != input_jur.upper():
                        continue

                # Filter by output jurisdiction (route must be from this jurisdiction)
                # e=>[?hu] means "email outputs from HU sources"
                if output_jur and route.get('jurisdiction'):
                    if route['jurisdiction'].upper() != output_jur.upper():
                        continue

                output_key = (output_name, route.get('source'), route.get('jurisdiction'))
                if output_key in seen_outputs:
                    continue
                seen_outputs.add(output_key)

                result['outputs'].append({
                    'output_type': output_name,
                    'output_code': output_code,
                    'source': route.get('source', 'unknown'),
                    'jurisdiction': route.get('jurisdiction'),
                    'method': route.get('method'),
                    'description': route.get('description', '')
                })

        # String-based fallback lookup
        for route_info in self.forward_routes_str.get(input_normalized, []):
            output_type = route_info['output']
            route = route_info['route']

            # Filter by input jurisdiction
            if input_jur and route.get('jurisdiction'):
                if route['jurisdiction'].upper() != input_jur.upper():
                    continue

            # Filter by output jurisdiction
            if output_jur and route.get('jurisdiction'):
                if route['jurisdiction'].upper() != output_jur.upper():
                    continue

            output_key = (output_type, route.get('source'), route.get('jurisdiction'))
            if output_key in seen_outputs:
                continue
            seen_outputs.add(output_key)

            result['outputs'].append({
                'output_type': output_type,
                'output_code': self.name_to_code.get(output_type),
                'source': route.get('source', 'unknown'),
                'jurisdiction': route.get('jurisdiction'),
                'method': route.get('method'),
                'description': route.get('description', '')
            })

        # Find modules that take this input
        for mod in self.io_config.get('module_executors', {}).get(input_type, []):
            if mod.get('requires_jurisdiction') and not input_jur:
                continue  # Skip if requires jurisdiction but none provided

            result['sources'].append({
                'type': 'module',
                'module': mod.get('module'),
                'method': mod.get('method') or mod.get('function'),
                'requires_jurisdiction': mod.get('requires_jurisdiction', False)
            })

        # Find ES indices for this input type
        mapping = self.io_config.get('field_code_mappings', {}).get(str(input_code), {})
        if mapping:
            cluster = mapping.get('cluster')
            indices = self.io_config.get('cluster_to_indices', {}).get(cluster, [])
            for idx in indices:
                result['sources'].append({
                    'type': 'elasticsearch',
                    'index': idx,
                    'cluster': cluster
                })

        return result

    def _route_lookup(self, query: Dict) -> Dict:
        """Find route between two specific types."""
        input_type = query['input_type']
        output_type = query['output_type']
        input_jur = query.get('input_jurisdiction')
        output_jur = query.get('output_jurisdiction')

        input_code = self.get_code_for_type(input_type)
        output_code = self.get_code_for_type(output_type)

        input_name = self.legend.get(str(input_code), input_type) if input_code else input_type
        output_name = self.legend.get(str(output_code), output_type) if output_code else output_type

        result = {
            'query': f'{input_type}=>{output_type}',
            'question': f'How to get {output_name} from {input_name}?',
            'input_type': input_name,
            'output_type': output_name,
            'direct_routes': [],
            'chain_routes': []
        }

        # Find direct routes
        if input_code:
            for route_info in self.forward_routes.get(input_code, []):
                if route_info['output'] == output_code:
                    route = route_info['route']
                    result['direct_routes'].append({
                        'source': route.get('source'),
                        'method': route.get('method'),
                        'jurisdiction': route.get('jurisdiction'),
                        'description': route.get('description', '')
                    })

        # Find 2-hop chains (input -> intermediate -> output)
        if input_code and output_code and not result['direct_routes']:
            for route1 in self.forward_routes.get(input_code, []):
                intermediate = route1['output']
                for route2 in self.forward_routes.get(intermediate, []):
                    if route2['output'] == output_code:
                        intermediate_name = self.legend.get(str(intermediate), f'code_{intermediate}')
                        result['chain_routes'].append({
                            'via': intermediate_name,
                            'step1': {
                                'source': route1['route'].get('source'),
                                'description': route1['route'].get('description', '')
                            },
                            'step2': {
                                'source': route2['route'].get('source'),
                                'description': route2['route'].get('description', '')
                            }
                        })

        return result


def detect_entity_type(value: str) -> Optional[str]:
    """Auto-detect entity type from value if no prefix given."""
    # Email pattern
    if re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', value):
        return 'email'
    # Phone pattern (various formats)
    if re.match(r'^[\+]?[\d\s\-\(\)]{7,}$', value.replace(' ', '')):
        return 'phone'
    # LinkedIn URL pattern
    if re.search(r'linkedin\.com/(?:in|company)/', value, re.IGNORECASE):
        return 'linkedin_url'
    # Domain pattern
    if re.match(r'^[a-zA-Z0-9][a-zA-Z0-9-]*\.[a-zA-Z]{2,}$', value):
        return 'domain'
    # URL pattern
    if value.startswith('http://') or value.startswith('https://'):
        return 'domain'
    # Default to person (most common)
    return None


def normalize_linkedin_url(value: str) -> str:
    """Normalize a LinkedIn profile/company URL or slug to a canonical URL."""
    v = (value or "").strip().strip('"').strip("'").strip()
    if not v:
        return v

    v = v.lstrip("@")

    # Handle 'linkedin.com/...' or 'www.linkedin.com/...' or scheme-less.
    if re.match(r'^(?:https?://)?(?:www\.)?linkedin\.com/', v, re.IGNORECASE):
        if not v.lower().startswith(("http://", "https://")):
            v = "https://" + v
        v = re.sub(
            r'^https?://(?:[a-z]{2,3}\.)?(?:www\.)?linkedin\.com',
            'https://linkedin.com',
            v,
            flags=re.IGNORECASE,
        )
        v = v.split("?", 1)[0].split("#", 1)[0].rstrip("/")
        return v

    # Handle 'in/<slug>' or 'company/<slug>' forms.
    if re.match(r'^(?:in|company)/', v, re.IGNORECASE):
        v = f"https://linkedin.com/{v}"
        return v.split("?", 1)[0].split("#", 1)[0].rstrip("/")

    # Treat a bare slug as a profile username.
    if re.match(r'^[A-Za-z0-9][A-Za-z0-9-]{2,}$', v) and "/" not in v and " " not in v:
        return f"https://linkedin.com/in/{v}"

    return v


def normalize_linkedin_username(value: str) -> str:
    """Normalize a LinkedIn username/slug (accepts URL, in/<slug>, or bare slug)."""
    v = (value or "").strip().strip('"').strip("'").strip()
    if not v:
        return v

    v = v.lstrip("@")

    # URL → extract slug
    m = re.search(r'linkedin\.com/(?:in|company)/([^/?#]+)/?', v, re.IGNORECASE)
    if m:
        return m.group(1)

    # in/<slug> or company/<slug>
    m = re.match(r'^(?:in|company)/([^/?#]+)/?$', v, re.IGNORECASE)
    if m:
        return m.group(1)

    return v


_EMAIL_FIND_RE = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')
_DOMAIN_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9-]*\.[A-Za-z]{2,}$')


def _normalize_phone(value: str) -> str:
    v = (value or "").strip()
    if not v:
        return v
    digits = re.sub(r'\D', '', v)
    if not digits:
        return ""
    if v.startswith("+"):
        return f"+{digits}"
    return digits


def _extract_pivot_entities(obj: Any) -> Dict[str, List[str]]:
    """Extract pivotable IO entities (emails/phones/domains/linkedin/usernames) from arbitrary JSON."""
    found = {
        "email": set(),
        "phone": set(),
        "domain": set(),
        "linkedin_url": set(),
        "linkedin_username": set(),
        "username": set(),
    }

    ignore_domains = {"localhost"}

    def add_domain(candidate: str):
        d = (candidate or "").strip().lower()
        if not d:
            return
        if d.startswith("www."):
            d = d[4:]
        if ":" in d:
            d = d.split(":", 1)[0]
        if d in ignore_domains:
            return
        if _DOMAIN_RE.match(d):
            found["domain"].add(d)

    def add_email(candidate: str):
        e = (candidate or "").strip().lower()
        if not e:
            return
        if _EMAIL_FIND_RE.fullmatch(e):
            found["email"].add(e)
            parts = e.split("@", 1)
            if len(parts) == 2:
                add_domain(parts[1])

    def add_phone(candidate: str):
        p = _normalize_phone(candidate)
        if not p:
            return
        if len(re.sub(r'\D', '', p)) < 7:
            return
        found["phone"].add(p)

    def add_linkedin(candidate: str):
        url = normalize_linkedin_url(candidate)
        if url and re.search(r'linkedin\.com/(?:in|company)/', url, re.IGNORECASE):
            found["linkedin_url"].add(url)
            slug = normalize_linkedin_username(url)
            if slug and slug != url:
                found["linkedin_username"].add(slug)

    def add_username(candidate: str):
        u = (candidate or "").strip()
        if not u:
            return
        if len(u) > 64 or " " in u or "/" in u or "@" in u:
            return
        found["username"].add(u)

    def walk(value: Any, key: str | None = None):
        if value is None:
            return
        if isinstance(value, dict):
            for k, v in value.items():
                walk(v, str(k) if k is not None else None)
            return
        if isinstance(value, list):
            for item in value:
                walk(item, key)
            return
        if not isinstance(value, str):
            return

        s = value.strip()
        if not s:
            return

        key_lower = (key or "").lower()

        # Always detect LinkedIn URLs and emails.
        if "linkedin.com/" in s.lower():
            add_linkedin(s)
        if "@" in s:
            for email in _EMAIL_FIND_RE.findall(s):
                add_email(email)

        # URL → domain extraction (and LinkedIn normalization)
        if s.lower().startswith(("http://", "https://")):
            try:
                from urllib.parse import urlparse
                parsed = urlparse(s)
                if parsed.netloc:
                    add_domain(parsed.netloc)
            except Exception:
                pass

        # Keyed extraction (safer than heuristic-only for phones/usernames)
        if "phone" in key_lower or key_lower in {"tel", "telephone", "mobile"}:
            add_phone(s)
        if "domain" in key_lower or "website" in key_lower or key_lower in {"url", "company_domain"}:
            if _DOMAIN_RE.match(s.lower()):
                add_domain(s)
        if "linkedin" in key_lower or key_lower in {"profile_url", "linkedin_url"}:
            add_linkedin(s)
        if key_lower == "username" or key_lower.endswith("_username") or "handle" in key_lower:
            add_username(s)

    walk(obj, None)

    return {k: sorted(v) for k, v in found.items() if v}


# =============================================================================
# RULE EXECUTOR - Executes rules using their resources field
# =============================================================================

class RuleExecutor:
    """Execute rules dynamically using their resources field from rules.json.

    Supports resource types:
    - script: Run Python script via subprocess
    - api: Call REST API endpoint
    - module: Import and call Python module method
    - url/search_url_template: Scrape URL via BrightData/Firecrawl
    """

    def __init__(self, project_id: str = None):
        self._brightdata_api_key = os.environ.get('BRIGHTDATA_API_KEY')
        self._session = None
        self.project_id = project_id  # For node creation in cymonides-1-{projectId}

    async def _get_session(self):
        """Lazy init aiohttp session."""
        if self._session is None:
            import aiohttp
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        """Close aiohttp session."""
        if self._session:
            await self._session.close()
            self._session = None

    def build_inputs(self, value: str, rule: Dict) -> Dict:
        """Build inputs dict from value based on rule's requires_any field."""
        inputs = {'query': value, 'value': value}

        # Get what field codes this rule requires
        requires = rule.get('requires_any', [])

        # Map common field codes to variable names
        code_to_var = {
            1: 'email', 2: 'phone', 3: 'username', 5: 'linkedin_url',
            6: 'domain', 7: 'person_name', 13: 'company_name', 14: 'company_id',
            129: 'domain_url', 147: 'keyword'
        }

        for code in requires:
            if code in code_to_var:
                inputs[code_to_var[code]] = value

        # Add common aliases
        inputs['name'] = value
        inputs['company'] = value

        return inputs

    async def execute_rule(self, rule: Dict, value: str, jurisdiction: str = None) -> Dict:
        """Execute a rule using its resources field."""
        rule_id = rule.get('id', 'unknown')
        resources = rule.get('resources', [])

        if not resources:
            # Try search_url_template as fallback
            template = rule.get('search_url_template')
            if template:
                resources = [{'type': 'url', 'url': template}]
            else:
                return {
                    'rule_id': rule_id,
                    'status': 'no_resources',
                    'note': 'Rule has no executable resources'
                }

        inputs = self.build_inputs(value, rule)
        if jurisdiction:
            inputs['jurisdiction'] = jurisdiction

        results = []
        success = False

        for resource in resources:
            try:
                res_type = resource.get('type', 'url')

                if res_type == 'script':
                    result = await self._run_script(resource, inputs)
                elif res_type == 'api':
                    result = await self._call_api(resource, inputs)
                elif res_type == 'module':
                    result = await self._call_module(resource, inputs)
                elif res_type in ('url', 'search_url_template', 'external'):
                    result = await self._scrape_url(resource, inputs)
                elif res_type == 'bang':
                    result = await self._execute_bang(resource, inputs)
                elif res_type == 'dataset':
                    result = await self._load_dataset(resource, inputs)
                elif res_type == 'database':
                    result = await self._query_database(resource, inputs)
                elif res_type == 'elastic':
                    result = await self._query_elastic(resource, inputs)
                elif res_type == 'brute_search':
                    result = await self._execute_brute_search(resource, inputs)
                elif res_type == 'search':
                    result = await self._execute_search(resource, inputs)
                elif res_type in ('corporate_registry', 'regulatory_filings', 'leak_database',
                                  'enforcement_actions', 'investigative_journalism',
                                  'regulatory_database', 'corporate_disclosures'):
                    # Metadata-only resources - treat as URL scraping if URL present
                    if resource.get('url'):
                        result = await self._scrape_url(resource, inputs)
                    else:
                        result = {
                            'type': res_type,
                            'name': resource.get('name', 'Unknown'),
                            'note': 'Metadata reference only - manual lookup required',
                            'access': resource.get('access', 'unknown')
                        }
                elif res_type == 'service':
                    result = {'type': 'service', 'note': 'Node.js services not supported in Python'}
                else:
                    result = {'error': f'Unknown resource type: {res_type}'}

                results.append(result)
                if result.get('success') or result.get('data'):
                    success = True

            except Exception as e:
                results.append({'error': str(e), 'resource': resource})

        return {
            'rule_id': rule_id,
            'label': rule.get('label'),
            'status': 'success' if success else 'failed',
            'results': results,
            'jurisdiction': jurisdiction
        }

    async def _run_script(self, resource: Dict, inputs: Dict) -> Dict:
        """Run a Python script via subprocess."""
        exec_cmd = resource.get('exec', '')
        path = resource.get('path', '')

        if not exec_cmd and path:
            exec_cmd = f'python3 {path}'

        # Substitute inputs: {domain} -> inputs['domain']
        for key, val in inputs.items():
            exec_cmd = exec_cmd.replace(f'{{{key}}}', str(val))

        try:
            proc = await asyncio.create_subprocess_shell(
                exec_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(BACKEND_PATH)
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)

            return {
                'type': 'script',
                'path': path,
                'success': proc.returncode == 0,
                'output': stdout.decode()[:5000],  # Limit output size
                'error': stderr.decode()[:1000] if proc.returncode != 0 else None
            }
        except asyncio.TimeoutError:
            return {'type': 'script', 'path': path, 'error': 'Timeout after 60s'}
        except Exception as e:
            return {'type': 'script', 'path': path, 'error': str(e)}

    async def _call_api(self, resource: Dict, inputs: Dict) -> Dict:
        """Call a REST API endpoint."""
        url = resource.get('url', '')

        # Substitute inputs in URL
        for key, val in inputs.items():
            url = url.replace(f'{{{key}}}', str(val))

        try:
            session = await self._get_session()
            async with session.get(url, timeout=30) as resp:
                if resp.content_type == 'application/json':
                    data = await resp.json()
                else:
                    data = await resp.text()

                return {
                    'type': 'api',
                    'url': url,
                    'success': resp.status == 200,
                    'status_code': resp.status,
                    'data': data if resp.status == 200 else None
                }
        except Exception as e:
            return {'type': 'api', 'url': url, 'error': str(e)}

    async def _call_module(self, resource: Dict, inputs: Dict) -> Dict:
        """Import and call a Python module method."""
        module_path = resource.get('import', '')
        method_name = resource.get('method', '')

        try:
            import importlib

            # Handle nested paths like "corporella.exa_company_search.ExaCompanySearch"
            parts = module_path.rsplit('.', 1)
            if len(parts) == 2:
                mod = importlib.import_module(parts[0])
                cls_or_func = getattr(mod, parts[1])
            else:
                mod = importlib.import_module(module_path)
                cls_or_func = mod

            # If it's a class, instantiate and get method
            if hasattr(cls_or_func, method_name):
                method = getattr(cls_or_func, method_name)
                if callable(method):
                    # Try to call with appropriate args
                    if asyncio.iscoroutinefunction(method):
                        result = await method(inputs.get('query', inputs.get('value')))
                    else:
                        result = method(inputs.get('query', inputs.get('value')))

                    return {
                        'type': 'module',
                        'module': module_path,
                        'method': method_name,
                        'success': True,
                        'data': result
                    }

            return {'type': 'module', 'error': f'Method {method_name} not found'}

        except ImportError as e:
            return {'type': 'module', 'module': module_path, 'error': f'Import failed: {e}'}
        except Exception as e:
            return {'type': 'module', 'module': module_path, 'error': str(e)}

    async def _scrape_url(self, resource: Dict, inputs: Dict) -> Dict:
        """Scrape a URL using BrightData or fallback to basic fetch."""
        url = resource.get('url', resource.get('search_url_template', ''))

        # Substitute inputs
        for key, val in inputs.items():
            url = url.replace(f'{{{key}}}', str(val))
            url = url.replace(f'{{{key.upper()}}}', str(val))

        # URL encode the query if still has unsubstituted placeholders
        import urllib.parse
        if '{query}' in url:
            url = url.replace('{query}', urllib.parse.quote(inputs.get('query', '')))

        try:
            # Try BrightData if available
            if self._brightdata_api_key:
                return await self._brightdata_scrape(url)

            # Fallback to basic fetch
            session = await self._get_session()
            async with session.get(url, timeout=30) as resp:
                html = await resp.text()
                return {
                    'type': 'url',
                    'url': url,
                    'success': resp.status == 200,
                    'content_length': len(html),
                    'preview': html[:500] if resp.status == 200 else None
                }
        except Exception as e:
            return {'type': 'url', 'url': url, 'error': str(e)}

    async def _brightdata_scrape(self, url: str) -> Dict:
        """Scrape URL via BrightData Web Unlocker (bypasses bot detection/CAPTCHAs)."""
        try:
            session = await self._get_session()

            # BrightData Web Unlocker API (for scraping protected pages, NOT for SERP)
            api_url = "https://api.brightdata.com/request"
            headers = {
                "Authorization": f"Bearer {self._brightdata_api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "zone": "web_unlocker",
                "url": url,
                "format": "raw"
            }

            async with session.post(api_url, json=payload, headers=headers, timeout=60) as resp:
                if resp.status == 200:
                    content = await resp.text()
                    return {
                        'type': 'brightdata',
                        'url': url,
                        'success': True,
                        'content_length': len(content),
                        'preview': content[:1000]
                    }
                else:
                    return {
                        'type': 'brightdata',
                        'url': url,
                        'error': f'BrightData returned {resp.status}'
                    }
        except Exception as e:
            return {'type': 'brightdata', 'url': url, 'error': str(e)}

    async def _execute_bang(self, resource: Dict, inputs: Dict) -> Dict:
        """Execute a bang pattern (e.g., !icij {query} -> search URL)."""
        pattern = resource.get('pattern', '')
        query = inputs.get('query', inputs.get('value', ''))

        # Bang patterns like "!icij {query}" map to search URLs
        bang_to_url = {
            '!icij': 'https://offshoreleaks.icij.org/search?q={query}',
            '!sec': 'https://www.sec.gov/cgi-bin/browse-edgar?company={query}&type=&owner=include&count=40&action=getcompany',
            '!oc': 'https://opencorporates.com/companies?q={query}',
            '!ch': 'https://find-and-update.company-information.service.gov.uk/search?q={query}',
            '!linkedin': 'https://www.linkedin.com/search/results/all/?keywords={query}',
        }

        # Extract bang from pattern
        import urllib.parse
        bang = pattern.split()[0] if pattern else ''
        if bang in bang_to_url:
            url = bang_to_url[bang].replace('{query}', urllib.parse.quote(query))
            return await self._scrape_url({'url': url}, inputs)

        return {
            'type': 'bang',
            'pattern': pattern,
            'note': f'Bang pattern {bang} not mapped to URL yet',
            'query': query
        }

    async def _load_dataset(self, resource: Dict, inputs: Dict) -> Dict:
        """Load data from a local JSON dataset file."""
        path = resource.get('path', '')
        query = inputs.get('query', inputs.get('value', ''))

        try:
            # Resolve path relative to project
            full_path = PROJECT_ROOT / path
            if not full_path.exists():
                full_path = MATRIX_DIR / path

            if not full_path.exists():
                return {'type': 'dataset', 'path': path, 'error': 'File not found'}

            with open(full_path) as f:
                data = json.load(f)

            # If data is a list, filter by query
            if isinstance(data, list):
                matches = [
                    item for item in data
                    if query.lower() in str(item).lower()
                ][:50]  # Limit results
                return {
                    'type': 'dataset',
                    'path': path,
                    'success': True,
                    'total_records': len(data),
                    'matches': len(matches),
                    'data': matches
                }

            return {
                'type': 'dataset',
                'path': path,
                'success': True,
                'data': data
            }

        except Exception as e:
            return {'type': 'dataset', 'path': path, 'error': str(e)}

    async def _query_database(self, resource: Dict, inputs: Dict) -> Dict:
        """Execute a SQLite database query."""
        db_name = resource.get('name', '')
        query_template = resource.get('query', '')
        value = inputs.get('query', inputs.get('value', ''))

        try:
            import sqlite3

            # Find database file
            db_path = PROJECT_ROOT / 'data' / db_name
            if not db_path.exists():
                db_path = BACKEND_PATH / db_name

            if not db_path.exists():
                return {'type': 'database', 'name': db_name, 'error': 'Database not found'}

            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Execute query with parameter
            cursor.execute(query_template, (value,))
            rows = cursor.fetchall()

            # Convert to dicts
            results = [dict(row) for row in rows[:100]]  # Limit results
            conn.close()

            return {
                'type': 'database',
                'name': db_name,
                'success': True,
                'rows': len(results),
                'data': results
            }

        except Exception as e:
            return {'type': 'database', 'name': db_name, 'error': str(e)}

    async def _query_elastic(self, resource: Dict, inputs: Dict) -> Dict:
        """Query Elasticsearch unified indices with filter and aggregation support.

        Resource format:
        {
            "type": "elastic",
            "index": "companies_unified",
            "search_fields": ["name^3", "legal_name^3", "domain^2"],
            "filter_fields": {
                "country": {"es_field": "country", "type": "term"},
                "municipality": {"es_field": "city", "type": "term"},
                "industry": {"es_field": "industry", "type": "term"},
                "founding_year": {"es_field": "founding_date", "type": "prefix"}
            },
            "return_fields": ["name", "domain", "country", "industry"],
            "aggregations": {
                "industries": {"field": "industry", "size": 50},
                "countries": {"field": "country", "size": 100}
            },
            "size": 50,
            "auto_create_nodes": ["company", "municipality", "industry"]
        }

        Inputs can include:
        - query/value: Text search query
        - country, municipality, industry, etc.: Filter values
        """
        index = resource.get('index', '')
        search_fields = resource.get('search_fields', ['name'])
        filter_fields = resource.get('filter_fields', {})
        return_fields = resource.get('return_fields', [])
        aggregations = resource.get('aggregations', {})
        auto_create_nodes = resource.get('auto_create_nodes', [])
        size = resource.get('size', 50)

        # Get search query (optional for filter-only searches)
        query = inputs.get('query', inputs.get('value', ''))

        if not index:
            return {'type': 'elastic', 'index': index, 'error': 'Missing index'}

        # Parse inline operators from query (industry:, sector:, size:, employees:, country:, city:)
        # Only for company searches
        parsed_filters = {}
        if 'companies' in index and query:
            try:
                import sys
                cymonides_dir = Path(__file__).resolve().parents[2] / "BACKEND" / "modules" / "CYMONIDES"
                cymonides_path = str(cymonides_dir)
                if cymonides_path not in sys.path:
                    sys.path.insert(0, cymonides_path)
                from industry_matcher import parse_all_operators
                parsed = parse_all_operators(query)
                if parsed['has_filters']:
                    parsed_filters = parsed['filters']
                    query = parsed['remaining_query']  # Remove operators from query

                    # Merge parsed filters into inputs
                    for k, v in parsed_filters.items():
                        if k not in inputs or not inputs[k]:
                            inputs[k] = v
            except ImportError as e:
                logger.warning(f"Industry matcher not available: {e}")

        # At least one of query or filter required
        has_filters = any(inputs.get(k) for k in filter_fields.keys()) or parsed_filters
        if not query and not has_filters:
            return {'type': 'elastic', 'index': index, 'error': 'Missing query or filters'}

        try:
            from elasticsearch import Elasticsearch

            es_url = os.environ.get('ELASTICSEARCH_URL', 'http://localhost:9200')
            es = Elasticsearch([es_url])

            # Build bool query
            bool_query = {"must": [], "should": [], "filter": []}

            # Add text search if query provided
            if query and search_fields:
                base_fields = [f.split('^')[0] for f in search_fields]
                bool_query["should"].extend([
                    {
                        "multi_match": {
                            "query": query,
                            "fields": search_fields,
                            "type": "best_fields",
                            "fuzziness": "AUTO"
                        }
                    },
                    {
                        "multi_match": {
                            "query": query,
                            "fields": base_fields,
                            "type": "phrase_prefix"
                        }
                    }
                ])
                bool_query["minimum_should_match"] = 1

            # Add filters from inputs
            for filter_name, filter_config in filter_fields.items():
                filter_value = inputs.get(filter_name)
                if filter_value:
                    es_field = filter_config.get('es_field', filter_name)
                    filter_type = filter_config.get('type', 'term')

                    if filter_type == 'term':
                        bool_query["filter"].append({"term": {es_field: filter_value}})
                    elif filter_type == 'prefix':
                        bool_query["filter"].append({"prefix": {es_field: filter_value}})
                    elif filter_type == 'range':
                        # Support range filters: {"min": X, "max": Y} or just value for >=
                        if isinstance(filter_value, dict):
                            range_q = {}
                            if 'min' in filter_value:
                                range_q['gte'] = filter_value['min']
                            if 'max' in filter_value:
                                range_q['lte'] = filter_value['max']
                            bool_query["filter"].append({"range": {es_field: range_q}})
                        else:
                            bool_query["filter"].append({"range": {es_field: {"gte": filter_value}}})
                    elif filter_type == 'terms':
                        # Multiple values
                        values = filter_value if isinstance(filter_value, list) else [filter_value]
                        bool_query["filter"].append({"terms": {es_field: values}})

            # Clean up empty clauses
            if not bool_query["must"]:
                del bool_query["must"]
            if not bool_query["should"]:
                del bool_query["should"]
            if not bool_query["filter"]:
                del bool_query["filter"]

            # Build ES query
            es_query = {
                "query": {"bool": bool_query} if bool_query else {"match_all": {}},
                "size": size,
                "_source": return_fields if return_fields else True
            }

            # Add aggregations if specified
            if aggregations:
                es_query["aggs"] = {}
                for agg_name, agg_config in aggregations.items():
                    es_query["aggs"][agg_name] = {
                        "terms": {
                            "field": agg_config.get('field'),
                            "size": agg_config.get('size', 50)
                        }
                    }

            # Execute search
            try:
                result = es.search(index=index, body=es_query)
            except Exception as search_err:
                # Fallback to simpler query
                fallback_query = {"match_all": {}}
                if query:
                    base_fields = [f.split('^')[0] for f in search_fields] if search_fields else ['name']
                    fallback_query = {"multi_match": {"query": query, "fields": base_fields, "type": "best_fields"}}
                es_query = {"query": fallback_query, "size": size, "_source": return_fields if return_fields else True}
                result = es.search(index=index, body=es_query)

            hits = result.get('hits', {})
            total = hits.get('total', {})
            total_count = total.get('value', 0) if isinstance(total, dict) else total

            records = []
            for hit in hits.get('hits', []):
                record = hit.get('_source', {})
                record['_id'] = hit.get('_id')
                record['_score'] = hit.get('_score')
                records.append(record)

            # Parse aggregations
            agg_results = {}
            if 'aggregations' in result:
                for agg_name, agg_data in result['aggregations'].items():
                    buckets = agg_data.get('buckets', [])
                    agg_results[agg_name] = [
                        {'key': b.get('key'), 'count': b.get('doc_count')}
                        for b in buckets
                    ]

            response = {
                'type': 'elastic',
                'index': index,
                'success': True,
                'total': total_count,
                'returned': len(records),
                'data': records,
                'filters_applied': {k: inputs.get(k) for k in filter_fields.keys() if inputs.get(k)},
                'auto_create_nodes': auto_create_nodes
            }

            if agg_results:
                response['aggregations'] = agg_results

            # Auto-create nodes if configured and we have a project_id
            if auto_create_nodes and records and self.project_id:
                try:
                    from atlas_node_creator import create_nodes_from_atlas_results
                    node_result = await create_nodes_from_atlas_results(
                        results=records,
                        source_index=index,
                        project_id=self.project_id,
                        root_entity=inputs.get('root_entity'),
                        auto_create_types=auto_create_nodes
                    )
                    response['nodes_created'] = node_result
                except Exception as node_err:
                    response['node_creation_error'] = str(node_err)

            return response

        except ImportError:
            return {'type': 'elastic', 'index': index, 'error': 'elasticsearch package not installed'}
        except Exception as e:
            return {'type': 'elastic', 'index': index, 'error': str(e)}

    async def _execute_brute_search(self, resource: Dict, inputs: Dict) -> Dict:
        """Execute BruteSearch via Node.js API endpoint.

        BruteSearch configuration from resource (supports two formats):

        Format 1 (rules.json):
        {
            "type": "brute_search",
            "engines": ["LI", "SS", "GK", "GO", "BI"],
            "wave": "instant_start",
            "query_template": "\"{person_name}\" email OR phone"
        }

        Format 2 (brute_search_rules.json):
        {
            "type": "brute_search",
            "config": {
                "engines": ["GO", "BI", "PX", "BR", "FC"],
                "wave": "instant_start",
                "mode": "balanced",
                "userLocation": {"country": "GB"},
                "newsCategories": ["business", "tech"],
                "timeoutSeconds": 180
            },
            "query_template": "\"{company_name}\" officers OR directors"
        }

        Calls: GET http://localhost:3000/api/search/stream/brute
        Returns aggregated results from all engines with deduplication.
        """
        # Support both flat structure (rules.json) and nested config (brute_search_rules.json)
        if 'config' in resource:
            config = resource['config']
        else:
            # Flatten top-level fields into config
            config = {
                'engines': resource.get('engines', []),
                'wave': resource.get('wave'),
                'mode': resource.get('mode', 'balanced')
            }

        if inputs.get('jurisdiction') and not config.get('userLocation'):
            config['userLocation'] = {'country': str(inputs['jurisdiction'])}

        query_template = resource.get('query_template', '{query}')

        # Build query from template
        query = query_template
        for key, val in inputs.items():
            query = query.replace(f'{{{key}}}', str(val))
            query = query.replace(f'{{{key.upper()}}}', str(val))

        # Node.js server URL from .env - Defaulting to Python Backend (8000) for Unified Architecture
        node_server_url = 'http://localhost:8000'

        try:
            session = await self._get_session()

            # Build query parameters from config
            params = {
                'query': query,
                'maxResults': config.get('maxResults', 10000),
                'timeoutSeconds': config.get('timeoutSeconds', 180)
            }

            # Add optional parameters
            if 'mode' in config:
                params['mode'] = config['mode']

            if 'userLocation' in config and 'country' in config['userLocation']:
                params['geo'] = config['userLocation']['country']

            if 'language' in config:
                params['language'] = config['language']

            if 'newsCategories' in config:
                params['newsCategories'] = ','.join(config['newsCategories'])

            if 'newsCountries' in config:
                params['newsCountries'] = ','.join(config['newsCountries'])

            if 'newsLanguages' in config:
                params['newsLanguages'] = ','.join(config['newsLanguages'])

            # BruteSearch-specific options
            if 'includeKeywordVariations' in config:
                params['includeKeywordVariations'] = str(config['includeKeywordVariations']).lower()

            if 'includeLinklaterEnrichment' in config:
                params['includeLinklaterEnrichment'] = str(config['includeLinklaterEnrichment']).lower()

            if 'includeTemplateEngines' in config:
                params['includeTemplateEngines'] = str(config['includeTemplateEngines']).lower()

            if 'templateEngineLimit' in config:
                params['templateEngineLimit'] = str(config['templateEngineLimit'])

            # Streaming endpoint (we'll consume the full stream)
            url = f"{node_server_url}/api/search/stream/brute"

            # Call the streaming endpoint and consume all events
            results = []
            engines_used = []
            metadata = {}

            async with session.get(url, params=params, timeout=params['timeoutSeconds'] + 10) as resp:
                if resp.status != 200:
                    return {
                        'type': 'brute_search',
                        'query': query,
                        'error': f'BruteSearch API returned {resp.status}',
                        'url': url
                    }

                # Parse SSE stream
                async for line in resp.content:
                    line_str = line.decode('utf-8').strip()

                    # SSE format: "data: {...}"
                    if line_str.startswith('data: '):
                        try:
                            data = json.loads(line_str[6:])  # Remove "data: " prefix

                            event_type = data.get('type')

                            if event_type == 'result':
                                # New result from an engine
                                results.extend(data.get('results', []))

                            elif event_type == 'engine_status':
                                # Engine completed
                                engine_code = data.get('engineCode')
                                if engine_code and engine_code not in engines_used:
                                    engines_used.append(engine_code)

                            elif event_type == 'complete':
                                # Search complete
                                metadata = data.get('metadata', {})
                                break

                            elif event_type == 'error':
                                return {
                                    'type': 'brute_search',
                                    'query': query,
                                    'error': data.get('message', 'Unknown error'),
                                    'engines_used': engines_used
                                }

                        except json.JSONDecodeError:
                            continue  # Skip malformed lines

            search_engine_hits = []
            seen_urls = set()
            for item in results:
                if not isinstance(item, dict):
                    continue
                url = item.get('url') or item.get('link') or item.get('href') or item.get('source_url')
                if not url:
                    continue
                url = str(url).strip()
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                search_engine_hits.append(url)
                if len(search_engine_hits) >= 100:
                    break

            return {
                'type': 'brute_search',
                'query': query,
                'success': True,
                'engines': config.get('engines', []),  # Requested engines
                'engines_used': engines_used,           # Actually executed engines
                'wave': config.get('wave', 'unknown'),
                'mode': config.get('mode', 'balanced'),
                'results_count': len(results),
                'unique_count': metadata.get('uniqueCount', len(results)),
                'results': results[:100],  # Limit output (full results in streaming)
                'search_engine_hits': search_engine_hits,
                'metadata': metadata,
                'url': url
            }

        except asyncio.TimeoutError:
            return {
                'type': 'brute_search',
                'query': query,
                'error': f'Timeout after {params["timeoutSeconds"]}s',
                'engines': config.get('engines', [])
            }

        except Exception as e:
            return {
                'type': 'brute_search',
                'query': query,
                'error': str(e),
                'engines': config.get('engines', [])
            }

    async def _execute_search(self, resource: Dict, inputs: Dict) -> Dict:
        """Execute a simple search query using specified engines.

        Resource format (from rules.json):
        {
            "type": "search",
            "query": "site:linkedin.com/in \"{person_name}\"",
            "engines": ["google", "bing"]
        }

        This is a simplified version of brute_search for basic queries.
        Uses the same brute search API but with simpler parameters.
        """
        query_template = resource.get('query', '{query}')
        engines = resource.get('engines', ['google', 'bing'])

        # Build query from template
        query = query_template
        for key, val in inputs.items():
            query = query.replace(f'{{{key}}}', str(val))
            query = query.replace(f'{{{key.upper()}}}', str(val))

        # Map engine names to codes (google->GO, bing->BI)
        engine_map = {
            'google': 'GO', 'bing': 'BI', 'duckduckgo': 'DD', 'brave': 'BR',
            'yandex': 'YO', 'perplexity': 'PX', 'exa': 'EX'
        }
        engine_codes = [engine_map.get(e.lower(), e.upper()) for e in engines]

        # Use brute search handler with simplified config
        brute_resource = {
            'type': 'brute_search',
            'engines': engine_codes,
            'wave': 'instant_start',
            'mode': 'speed',
            'query_template': query
        }

        return await self._execute_brute_search(brute_resource, inputs)


# =============================================================================
# CONFIG-DRIVEN ROUTER - Routes investigations using IO_INTEGRATION.json
# =============================================================================

class ConfigDrivenRouter:
    """Routes investigations using IO_INTEGRATION.json as the single source of truth.

    This replaces hardcoded investigation methods with config-driven routing.
    All sources (ES indices + backend modules) are defined in IO_INTEGRATION.json.
    """

    # Path to IO_INTEGRATION.json config
    IO_INTEGRATION_PATH = resolve_io_integration_path()

    # Entity type to field code mapping
    TYPE_TO_CODE = {
        'email': 1, 'phone': 2, 'username': 3, 'linkedin_url': 5, 'linkedin_username': 5,
        'domain': 6, 'person': 7, 'company': 13, 'company_reg_id': 14,
        'address': 20, 'ip_address': 21, 'url': 22, 'hash': 30, 'document': 40
    }

    def __init__(self):
        self.config = self._load_config()
        self.index_registry = self._load_index_registry()
        self._es_client = None
        self._module_cache = {}

    def _load_config(self) -> Dict:
        """Load IO_INTEGRATION.json config."""
        if self.IO_INTEGRATION_PATH.exists():
            with open(self.IO_INTEGRATION_PATH) as f:
                return json.load(f)
        return {}

    def _load_index_registry(self) -> Dict[str, Any]:
        """Load INDEX_REGISTRY.json to discover queryable fields per index."""
        candidates = [
            self.IO_INTEGRATION_PATH.parent / "INDEX_REGISTRY.json",
            PROJECT_ROOT / "CYMONIDES" / "metadata" / "index_registry" / "INDEX_REGISTRY.json",
        ]
        for candidate in candidates:
            if candidate.exists():
                try:
                    with open(candidate) as f:
                        data = json.load(f)
                    return data.get("indices", {})
                except Exception:
                    continue
        return {}

    def _get_term_fields_for_index(self, index: str) -> List[str]:
        """Best-effort list of keyword-like fields for term queries."""
        entry = self.index_registry.get(index, {})
        key_fields = entry.get("key_fields", {}) if isinstance(entry, dict) else {}
        fields = []
        for field_name, meta in key_fields.items():
            if not isinstance(meta, dict):
                continue
            ftype = str(meta.get("type", "")).lower()
            if ftype in {"keyword", "ip", "date"}:
                fields.append(field_name)
        return fields

    def _get_es_client(self):
        """Lazy-load Elasticsearch client."""
        if self._es_client is None:
            try:
                from elasticsearch import Elasticsearch
                es_url = os.environ.get('ELASTICSEARCH_URL', 'http://localhost:9200')
                self._es_client = Elasticsearch([es_url])
            except ImportError:
                pass
        return self._es_client

    def get_field_code(self, entity_type: str) -> int:
        """Convert entity type to field code."""
        return self.TYPE_TO_CODE.get(entity_type, 0)

    def get_sources_for_input(self, entity_type: str, jurisdiction: str = None) -> List[Dict]:
        """Get all sources (ES indices + modules) for an input type.

        Returns list of source configs with:
        - type: 'elasticsearch' or 'module'
        - index/module: Name of ES index or module path
        - query_type: 'term' or 'match'
        - priority: Execution order
        """
        sources = []
        field_code = self.get_field_code(entity_type)

        # 1. Get ES indices from field_code_mappings
        mapping = self.config.get("field_code_mappings", {}).get(str(field_code), {})
        if mapping:
            cluster = mapping.get("cluster", "")
            indices = mapping.get("indices") or self.config.get("cluster_to_indices", {}).get(cluster, [])
            query_type = mapping.get("query_type", "match")

            for idx in indices:
                sources.append({
                    "type": "elasticsearch",
                    "index": idx,
                    "cluster": cluster,
                    "query_type": query_type,
                    "priority": 100  # ES indices run first
                })

            # Also add fallback cluster indices
            for fallback_cluster in mapping.get("fallback_clusters", []):
                fallback_indices = self.config.get("cluster_to_indices", {}).get(fallback_cluster, [])
                for idx in fallback_indices:
                    if idx not in [s["index"] for s in sources if s["type"] == "elasticsearch"]:
                        sources.append({
                            "type": "elasticsearch",
                            "index": idx,
                            "cluster": fallback_cluster,
                            "query_type": query_type,
                            "priority": 200  # Fallback indices run after primary
                        })

        # 2. Get backend modules from module_executors
        module_configs = self.config.get("module_executors", {}).get(entity_type, [])
        for mod_config in module_configs:
            # Skip modules that require jurisdiction if not provided
            if mod_config.get("requires_jurisdiction") and not jurisdiction:
                continue

            sources.append({
                "type": "module",
                **mod_config
            })

        # Sort by priority
        sources.sort(key=lambda x: x.get("priority", 999))

        return sources

    async def execute_elasticsearch(self, index: str, value: str, query_type: str = "match") -> Dict:
        """Execute search against an Elasticsearch index."""
        es = self._get_es_client()
        if not es:
            return {"error": "Elasticsearch not available", "index": index}

        try:
            # Allow configs to reference indices that may not exist yet (e.g. cymonides-3 during consolidation)
            try:
                if not es.indices.exists(index=index):
                    return {"index": index, "status": "missing_index", "total": 0, "results": []}
            except Exception:
                # If existence check fails, fall back to attempting the search.
                pass

            if query_type == "term":
                term_fields = self._get_term_fields_for_index(index)
                if term_fields:
                    query = {
                        "bool": {
                            "should": [{"term": {field: value}} for field in term_fields],
                            "minimum_should_match": 1,
                        }
                    }
                else:
                    query = {"multi_match": {"query": value, "fields": ["*"]}}
            else:
                query = {"multi_match": {"query": value, "fuzziness": "AUTO", "fields": ["*"]}}

            result = es.search(index=index, body={"query": query, "size": 50})
            hits = result.get("hits", {}).get("hits", [])
            return {
                "index": index,
                "total": result.get("hits", {}).get("total", {}).get("value", 0),
                "results": [h.get("_source", {}) for h in hits]
            }
        except Exception as e:
            return {"error": str(e), "index": index}

    async def execute_module(self, mod_config: Dict, value: str, jurisdiction: str = None) -> Dict:
        """Execute a backend module (Torpedo, Corporella, EYE-D, LINKLATER)."""
        module_path = mod_config.get("module", "")
        method_name = mod_config.get("method") or mod_config.get("function")

        if not module_path or not method_name:
            return {"error": "Invalid module config", "config": mod_config}

        try:
            # Dynamic import
            import importlib

            python_module_path = module_path.replace("/", ".")
            if python_module_path.startswith("EYE-D."):
                python_module_path = "eyed." + python_module_path[len("EYE-D."):]
            elif python_module_path.startswith("EYE_D."):
                python_module_path = "eyed." + python_module_path[len("EYE_D."):]
            python_module_path = python_module_path.replace("-", "_")

            # Try to import from BACKEND/modules path
            try:
                mod = importlib.import_module(python_module_path)
            except ModuleNotFoundError:
                # Add path and try again
                for candidate in (BACKEND_PATH, PROJECT_ROOT):
                    if str(candidate) not in sys.path:
                        sys.path.insert(0, str(candidate))
                mod = importlib.import_module(python_module_path)

            # Get the handler (class method or function)
            if "class" in mod_config:
                # Instantiate class and call method
                cls = getattr(mod, mod_config["class"])
                instance = cls()

                # Call init method if specified (e.g., load_sources for Torpedo)
                init_method = mod_config.get("init_method")
                if init_method:
                    init_fn = getattr(instance, init_method)
                    if asyncio.iscoroutinefunction(init_fn):
                        await init_fn()
                    else:
                        init_fn()

                handler = getattr(instance, method_name)
            else:
                # Direct function call
                handler = getattr(mod, method_name)

            # Call the handler
            if asyncio.iscoroutinefunction(handler):
                if jurisdiction and not mod_config.get("requires_jurisdiction") == False:
                    result = await handler(value, jurisdiction)
                else:
                    result = await handler(value)
            else:
                if jurisdiction and not mod_config.get("requires_jurisdiction") == False:
                    result = handler(value, jurisdiction)
                else:
                    result = handler(value)

            return {
                "module": module_path,
                "method": method_name,
                "result": result
            }

        except Exception as e:
            return {"error": str(e), "module": module_path, "method": method_name}

    def lookup(self, entity_type: str, value: str = None, jurisdiction: str = None) -> Dict:
        """LOOKUP: Discover what sources can answer this query (no execution).

        Returns all sources (ES indices + modules) that would be queried for
        this entity type and jurisdiction, without actually executing them.

        This is the "planning" phase - shows routing without execution.

        Args:
            entity_type: Type of entity (person, company, email, domain, etc.)
            value: Optional value (not used for lookup, just echoed back)
            jurisdiction: Optional jurisdiction filter (e.g., 'HR', 'US', 'UK')

        Returns:
            Dict with sources list and routing info
        """
        sources = self.get_sources_for_input(entity_type, jurisdiction)

        # Format sources for display
        formatted_sources = []
        for source in sources:
            if source["type"] == "elasticsearch":
                formatted_sources.append({
                    "type": "elasticsearch",
                    "index": source["index"],
                    "cluster": source.get("cluster", "unknown"),
                    "query_type": source.get("query_type", "match")
                })
            elif source["type"] == "module":
                formatted_sources.append({
                    "type": "module",
                    "module": source.get("module", "unknown"),
                    "method": source.get("method") or source.get("function", "unknown"),
                    "requires_jurisdiction": source.get("requires_jurisdiction", False)
                })

        return {
            "entity_type": entity_type,
            "value": value,
            "jurisdiction": jurisdiction,
            "sources_count": len(sources),
            "sources": formatted_sources,
            "note": "Use run() to execute these sources"
        }

    async def run(self, entity_type: str, value: str, jurisdiction: str = None) -> Dict:
        """RUN: Execute investigation across ALL configured sources.

        This actually queries each source and returns results.

        Args:
            entity_type: Type of entity (person, company, email, domain, etc.)
            value: The value to search for
            jurisdiction: Optional jurisdiction filter (e.g., 'HR', 'US', 'UK')

        Returns:
            Dict with results from all sources
        """
        return await self.execute_all(entity_type, value, jurisdiction)

    async def execute_all(self, entity_type: str, value: str, jurisdiction: str = None) -> Dict:
        """Execute investigation across ALL configured sources.

        This is the internal execution method. Use run() as the public interface.
        1. Gets all sources for the entity type from IO_INTEGRATION.json
        2. Executes each source (ES indices + modules) in parallel
        3. Returns unified results
        """
        sources = self.get_sources_for_input(entity_type, jurisdiction)

        results = {
            "entity_type": entity_type,
            "value": value,
            "jurisdiction": jurisdiction,
            "sources_queried": [],
            "results": {},
            "errors": []
        }

        # Execute all sources in parallel
        async def execute_source(source: Dict) -> Tuple[str, Dict]:
            source_name = source.get("index") or source.get("module", "unknown")
            try:
                if source["type"] == "elasticsearch":
                    return source_name, await self.execute_elasticsearch(
                        source["index"], value, source.get("query_type", "match")
                    )
                elif source["type"] == "module":
                    return source_name, await self.execute_module(source, value, jurisdiction)
                else:
                    return source_name, {"error": f"Unknown source type: {source['type']}"}
            except Exception as e:
                return source_name, {"error": str(e)}

        tasks = [execute_source(source) for source in sources]
        task_results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, (source_name, result) in enumerate(task_results):
            if isinstance(result, Exception):
                results["errors"].append(f"{source_name}: {str(result)}")
            elif "error" in result:
                results["errors"].append(f"{source_name}: {result['error']}")
            else:
                results["sources_queried"].append(source_name)
                results["results"][source_name] = result

        return results


# =============================================================================
# IO EXECUTOR - Executes investigation pipelines
# =============================================================================

class IOExecutor:
    """Executes investigation pipelines based on entity type.

    Routes to appropriate modules:
    - Person (p:) -> EYE-D, sanctions, web enrichment
    - Company (c:) -> Corporella, OpenCorporates, Aleph, sanctions
    - Email (e:) -> EYE-D, breach checks, domain extraction
    - Phone (t:) -> EYE-D, carrier lookup
    - Domain (d:) -> WHOIS, backlinks, Wayback, GA tracker
    """

    def __init__(self, router: 'IORouter', dry_run: bool = False, project_id: str = None):
        self.router = router
        self.dry_run = dry_run
        self.project_id = project_id or 'default'
        self.results = {}
        self._modules_loaded = False
        self.rule_executor = RuleExecutor(project_id=self.project_id)  # Dynamic rule execution via resources field
        self._chain_executor = None  # Lazy-loaded ChainExecutor
        self._chain_rules = {}  # Chain rules loaded from chain_rules.json
        self._cookbook_executor = None  # Lazy-loaded CookbookExecutor for reactive slot-based investigations
        self._use_reactive_mode = os.environ.get('IO_REACTIVE_MODE', 'false').lower() == 'true'

    def _lazy_load_modules(self):
        """Lazy load execution modules to avoid import errors at startup."""
        if self._modules_loaded:
            return

        # Try to import modules - they may not all be available
        self._eye_d = None
        self._corporella = None
        self._firecrawl = None

        try:
            from unified_osint import UnifiedSearcher
            self._eye_d = UnifiedSearcher
        except ImportError:
            try:
                sys.path.insert(0, str(BACKEND_PATH / "EYE-D"))
                from unified_osint import UnifiedSearcher
                self._eye_d = UnifiedSearcher
            except ImportError:
                pass

        try:
            from corporella.exa_company_search import ExaCompanySearch
            self._corporella = ExaCompanySearch
        except ImportError:
            try:
                sys.path.insert(0, str(BACKEND_PATH / "corporella"))
                from exa_company_search import ExaCompanySearch
                self._corporella = ExaCompanySearch
            except ImportError:
                pass

        # WDC (Web Data Commons) - Schema.org entity index
        self._wdc = None
        try:
            sys.path.insert(0, str(BACKEND_PATH / "DEFINITIONAL"))
            from wdc_query import (
                WDCQueryService,
                search_person_entities,
                search_organization_entities,
                search_localbusiness_entities,
                search_product_entities,
            )
            self._wdc = WDCQueryService
            self._wdc_search_person = search_person_entities
            self._wdc_search_org = search_organization_entities
            self._wdc_search_local = search_localbusiness_entities
            self._wdc_search_product = search_product_entities
        except ImportError:
            pass

        # Torpedo - Country-specific company profile fetcher
        self._torpedo = None
        try:
            sys.path.insert(0, str(BACKEND_PATH))
            from TORPEDO.torpedo import Torpedo
            self._torpedo = Torpedo
        except ImportError:
            pass

        # Country APIs - Country-specific registry CLIs
        self._country_apis = {}
        # GLEIF is part of Corporella, not a country API
        excluded = {'GLEIF', '__pycache__', 'country_templates'}
        try:
            country_engines_path = BACKEND_PATH / "country_engines"
            sys.path.insert(0, str(country_engines_path))
            # Load available country CLIs
            for country_dir in country_engines_path.iterdir():
                if country_dir.is_dir() and country_dir.name not in excluded and not country_dir.name.startswith('_'):
                    cli_file = country_dir / f"{country_dir.name.lower()}_cli.py"
                    unified_cli = country_dir / f"{country_dir.name.lower()}_unified_cli.py"
                    if cli_file.exists() or unified_cli.exists():
                        self._country_apis[country_dir.name] = str(cli_file if cli_file.exists() else unified_cli)
        except Exception:
            pass

        # Social Media - Social platform searches (SocialSearcher)
        self._social = None
        try:
            sys.path.insert(0, str(BACKEND_PATH / "brute" / "engines"))
            from socialsearcher import SocialSearcher
            self._social = SocialSearcher
        except ImportError:
            pass

        # BrightData - Web scraping only (for protected registry sites with bot detection)
        # NOTE: For SERP search, use brute.py or Firecrawl search endpoint
        self._brightdata_api_key = os.environ.get('BRIGHTDATA_API_KEY')
        self._brightdata_available = bool(self._brightdata_api_key)

        # OCCRP Aleph - 237 collections across 75+ jurisdictions
        # Uses unified corporella/occrp_aleph.py module
        self._aleph = None
        self._aleph_collections = None
        try:
            sys.path.insert(0, str(BACKEND_PATH / "corporella"))
            from occrp_aleph import AlephSearcher
            self._aleph = AlephSearcher
            # Load Aleph collections mapping
            collections_path = MATRIX_DIR / "aleph_collections.json"
            if collections_path.exists():
                with open(collections_path) as f:
                    self._aleph_collections = json.load(f)
                logger.info(f"Loaded Aleph collections: {self._aleph_collections.get('meta', {}).get('total_collections', 0)} collections")
        except ImportError as e:
            logger.warning(f"OCCRP Aleph module not available: {e}")

        self._modules_loaded = True

    # =========================================================================
    # DYNAMIC RULE EXECUTION - Uses rules.json resources field
    # =========================================================================

    def _find_rule(self, rule_id: str) -> Optional[Dict]:
        """Find a rule by ID."""
        for rule in self.router.rules:
            if rule.get('id') == rule_id:
                return rule
        return None

    def _find_playbook(self, playbook_id: str) -> Optional[Dict]:
        """Find a playbook by ID."""
        for pb in self.router.playbooks:
            if pb.get('id') == playbook_id:
                return pb
        return None

    def _find_chain_rule(self, rule_id: str) -> Optional[Dict]:
        """Find a chain rule by ID.

        Chain rules are loaded from chain_rules.json and have a chain_config field.
        """
        if not self._chain_rules:
            # Lazy load chain rules
            chain_rules_path = MATRIX_DIR / "chain_rules.json"
            if chain_rules_path.exists():
                with open(chain_rules_path) as f:
                    chain_rules_list = json.load(f)
                    self._chain_rules = {rule['id']: rule for rule in chain_rules_list}

        return self._chain_rules.get(rule_id)

    def _get_chain_executor(self):
        """Lazy load ChainExecutor."""
        if self._chain_executor is None:
            from chain_executor import ChainExecutor
            self._chain_executor = ChainExecutor(self.rule_executor)
        return self._chain_executor

    def _get_cookbook_executor(self) -> Optional['CookbookExecutor']:
        """Lazy load CookbookExecutor for reactive slot-based investigations."""
        if self._cookbook_executor is None and COOKBOOK_EXECUTOR_AVAILABLE:
            self._cookbook_executor = CookbookExecutor(project_id=self.project_id)
        return self._cookbook_executor

    async def _execute_reactive(self, entity_type: str, value: str, jurisdiction: str) -> Dict[str, Any]:
        """Execute investigation using reactive CookbookExecutor.

        This uses EDITH templates with slot/trigger cascades instead of hardcoded pipelines.
        Requires jurisdiction to select appropriate cookbooks.

        Args:
            entity_type: 'company' or 'person'
            value: Entity name
            jurisdiction: Jurisdiction code (required for cookbook selection)

        Returns:
            Dict with sections, slots, completion status, and execution log
        """
        cookbook_exec = self._get_cookbook_executor()
        if not cookbook_exec:
            return {"error": "CookbookExecutor not available", "fallback": True}

        genre = f"{entity_type}_dd"  # company_dd or person_dd

        try:
            result = await cookbook_exec.execute_dd(
                jurisdiction=jurisdiction,
                genre=genre,
                entity=value,
                initial_slots={f"{entity_type}_name": value, "jurisdiction": jurisdiction}
            )
            result["routing"] = "reactive_cookbook"
            return result
        except Exception as e:
            logger.error(f"Reactive execution failed: {e}")
            return {"error": str(e), "fallback": True}

    async def execute_chain_rule(self, rule_id: str, value: str, jurisdiction: str = None) -> Dict:
        """Execute a chain rule (multi-hop recursive investigation).

        Chain rules have a chain_config that defines:
        - type: Strategy (recursive_expansion, cascading_ownership, etc.)
        - max_depth: Recursion limit
        - steps: Ordered sequence of actions

        Example:
            result = await executor.execute_chain_rule('CHAIN_OFFICER_TO_ALL_COMPANIES', 'John Smith')
            # Returns: { chain_type, depth_reached, total_results, unique_entities, results }
        """
        chain_rule = self._find_chain_rule(rule_id)
        if not chain_rule:
            return {'error': f'Chain rule not found: {rule_id}', 'rule_id': rule_id}

        if self.dry_run:
            chain_config = chain_rule.get('chain_config', {})
            return {
                'rule_id': rule_id,
                'label': chain_rule.get('label'),
                'status': 'dry_run',
                'chain_type': chain_config.get('type'),
                'max_depth': chain_config.get('max_depth'),
                'steps': chain_config.get('steps', []),
                'would_execute': True
            }

        # Execute chain
        chain_executor = self._get_chain_executor()
        initial_input = {'value': value}
        result = await chain_executor.execute_chain(chain_rule, initial_input, jurisdiction)

        return result

    async def execute_by_rule(self, rule_id: str, value: str, jurisdiction: str = None) -> Dict:
        """Execute a specific rule by ID using its resources field.

        This is the NEW dynamic execution path that uses the resources
        defined in rules.json instead of hardcoded module calls.

        If the rule has a chain_config, it will be executed as a multi-hop chain.

        Example:
            result = await executor.execute_by_rule('WHOIS_FROM_DOMAIN', 'acme.com')
            # Uses rule's resources: script, api, module, or url

            result = await executor.execute_by_rule('CHAIN_OFFICER_TO_ALL_COMPANIES', 'John Smith')
            # Executes recursive chain to find all companies + officers
        """
        # First check if this is a chain rule
        chain_rule = self._find_chain_rule(rule_id)
        if chain_rule:
            return await self.execute_chain_rule(rule_id, value, jurisdiction)

        # Regular rule execution
        rule = self._find_rule(rule_id)
        if not rule:
            return {'error': f'Rule not found: {rule_id}', 'rule_id': rule_id}

        if self.dry_run:
            return {
                'rule_id': rule_id,
                'label': rule.get('label'),
                'status': 'dry_run',
                'resources': rule.get('resources', []),
                'search_url_template': rule.get('search_url_template'),
                'would_execute': True
            }

        return await self.rule_executor.execute_rule(rule, value, jurisdiction)

    async def execute_playbook(self, playbook_id: str, value: str, jurisdiction: str = None,
                                parallel: bool = True) -> Dict:
        """Execute all rules in a playbook.

        Args:
            playbook_id: ID of playbook to execute
            value: Input value (company name, person name, etc.)
            jurisdiction: Optional jurisdiction filter
            parallel: If True, execute rules in parallel; else sequential

        Example:
            result = await executor.execute_playbook('PLAYBOOK_JUR_HU_COMPANY', 'MET Group')
        """
        playbook = self._find_playbook(playbook_id)
        if not playbook:
            return {'error': f'Playbook not found: {playbook_id}', 'playbook_id': playbook_id}

        rule_ids = playbook.get('rules', [])

        if self.dry_run:
            return {
                'playbook_id': playbook_id,
                'label': playbook.get('label'),
                'status': 'dry_run',
                'rules': rule_ids,
                'jurisdiction': playbook.get('jurisdiction'),
                'would_execute': True
            }

        start_time = datetime.now()
        results = []

        if parallel:
            # Execute all rules in parallel
            tasks = [
                self.execute_by_rule(rule_id, value, jurisdiction or playbook.get('jurisdiction'))
                for rule_id in rule_ids
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            # Convert exceptions to error dicts
            results = [
                r if isinstance(r, dict) else {'error': str(r)}
                for r in results
            ]
        else:
            # Execute sequentially
            for rule_id in rule_ids:
                result = await self.execute_by_rule(
                    rule_id, value, jurisdiction or playbook.get('jurisdiction')
                )
                results.append(result)

        # Count successes
        successes = sum(1 for r in results if r.get('status') == 'success')

        return {
            'playbook_id': playbook_id,
            'label': playbook.get('label'),
            'status': 'success' if successes > 0 else 'failed',
            'rules_executed': len(results),
            'rules_succeeded': successes,
            'duration_seconds': (datetime.now() - start_time).total_seconds(),
            'results': results
        }

    async def execute_matching_rules(self, input_code: int, value: str,
                                      jurisdiction: str = None, limit: int = 10) -> Dict:
        """Find and execute all rules that can process the given input type.

        Args:
            input_code: Field code (e.g., 13 for company_name, 6 for domain)
            value: The input value
            jurisdiction: Optional jurisdiction filter
            limit: Max number of rules to execute

        Example:
            # Execute all rules that take company_name as input
            result = await executor.execute_matching_rules(13, 'Acme Corp', 'US', limit=5)
        """
        matching_rules = []

        for rule in self.router.rules:
            requires = rule.get('requires_any', [])
            if input_code in requires:
                # Check jurisdiction if specified
                rule_jur = rule.get('jurisdiction', 'none')
                if jurisdiction and rule_jur not in ('none', jurisdiction, 'GLOBAL'):
                    continue
                matching_rules.append(rule)

        if not matching_rules:
            return {
                'input_code': input_code,
                'status': 'no_matching_rules',
                'value': value
            }

        # Limit and execute
        matching_rules = matching_rules[:limit]

        if self.dry_run:
            return {
                'input_code': input_code,
                'status': 'dry_run',
                'matching_rules': [r.get('id') for r in matching_rules],
                'would_execute': len(matching_rules)
            }

        # Execute in parallel
        tasks = [
            self.rule_executor.execute_rule(rule, value, jurisdiction)
            for rule in matching_rules
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        results = [r if isinstance(r, dict) else {'error': str(r)} for r in results]

        successes = sum(1 for r in results if r.get('status') == 'success')

        return {
            'input_code': input_code,
            'value': value,
            'status': 'success' if successes > 0 else 'failed',
            'rules_matched': len(matching_rules),
            'rules_succeeded': successes,
            'results': results
        }

    async def _run_reality_check(self, result: Dict) -> Dict:
        """Run Reality Engine (EventAssessor) on investigation results."""
        if not REALITY_ENGINE_AVAILABLE:
            return {"status": "skipped", "reason": "Reality Engine not found"}

        try:
            # 1. Adapt results to Graph State
            adapter = RealityEngineAdapter(result)
            
            # 2. Run Assessor
            assessor = EventAssessor(adapter)
            gaps = assessor.assess()

            # 3. Execute Gaps (Auto-Resolution)
            execution_results = []
            if gaps:
                executor = GapExecutor()
                
                async def search_runner(query: str):
                    # Use BruteSearch for resolution
                    resource = {
                        'type': 'brute_search',
                        'engines': ['GO', 'BI'], # Fast engines
                        'wave': 'instant_start',
                        'mode': 'speed',
                        'query_template': query
                    }
                    # rule_executor expects inputs dict
                    return await self.rule_executor._execute_brute_search(resource, {'query': query})

                for gap in gaps:
                    res = await executor.execute(gap, search_runner, adapter)
                    execution_results.append({
                        "gap_id": res.gap_id,
                        "status": res.status,
                        "resolved_query": res.resolved_query,
                        "result_count": res.data.get('results_count', 0) if res.data else 0
                        # We don't dump full data to keep output clean
                    })

            # 4. Format Output
            return {
                "status": "active",
                "gaps_detected": len(gaps),
                "gaps": [
                    {
                        "intent": g.intent,
                        "description": g.description,
                        "query": g.query,
                        "priority": g.priority
                    }
                    for g in gaps
                ],
                "gap_resolutions": execution_results
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    # =========================================================================
    # UNIFIED EXECUTION - Config-driven routing via IO_INTEGRATION.json
    # =========================================================================

    async def execute(self, entity_type: str, value: str, jurisdiction: str = None) -> Dict[str, Any]:
        """Run investigation pipeline for entity type using config-driven routing.

        This method uses ConfigDrivenRouter to execute ALL sources defined in
        IO_INTEGRATION.json for the given entity type. Sources include:
        - Elasticsearch indices (corporate, breach, person, domain clusters)
        - Backend modules (Torpedo, Corporella, EYE-D, LINKLATER)

        The routing is determined by IO_INTEGRATION.json, not hardcoded logic.
        """
        start_time = datetime.now()

        if self.dry_run:
            return self._dry_run_plan(entity_type, value, jurisdiction)

        # Use ConfigDrivenRouter for unified execution
        config_router = ConfigDrivenRouter()

        try:
            # Execute all sources via config-driven routing
            routing_value = value
            normalized_value = None
            if entity_type == "linkedin_url":
                normalized = normalize_linkedin_url(value)
                if normalized and normalized != value:
                    normalized_value = normalized
                    routing_value = normalized
            elif entity_type == "linkedin_username":
                normalized_value = normalize_linkedin_url(value)
                routing_value = normalized_value or value

            router_results = await config_router.execute_all(entity_type, routing_value, jurisdiction)

            result = {
                "entity_type": entity_type,
                "value": value,
                "normalized_value": normalized_value,
                "jurisdiction": jurisdiction,
                "timestamp": start_time.isoformat(),
                "modules_run": router_results.get("sources_queried", []),
                "results": router_results.get("results", {}),
                "errors": router_results.get("errors", []),
                "routing": "config_driven"  # Flag indicating new routing system
            }

            # Inject test flag for Reality Engine verification if value contains special trigger
            if "test_event_physics" in value:
                result["test_event_mode"] = True

            # SOCIAL MEDIA: Use custom handler since ConfigDrivenRouter doesn't cover it
            if entity_type == 'social_media':
                await self._social_media_investigation(value, result)

            # RUN REALITY ENGINE
            result["reality_check"] = await self._run_reality_check(result)

        except Exception as e:
            result = {
                "entity_type": entity_type,
                "value": value,
                "jurisdiction": jurisdiction,
                "timestamp": start_time.isoformat(),
                "modules_run": [],
                "results": {},
                "errors": [f"Pipeline error: {str(e)}"],
                "routing": "config_driven"
            }

        result["duration_seconds"] = (datetime.now() - start_time).total_seconds()
        return result

    async def execute_recursive(
        self,
        entity_type: str,
        value: str,
        jurisdiction: str = None,
        max_depth: int = 2,
        max_nodes: int = 50,
        recurse_types: Optional[List[str]] = None,
        persist_project: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Recursively pivot discovered entities back into IO execution.

        Runs breadth-first to keep expansion predictable and resource-safe.
        """
        if self.dry_run:
            plan = self._dry_run_plan(entity_type, value, jurisdiction)
            plan["recurse"] = {
                "enabled": True,
                "max_depth": max_depth,
                "max_nodes": max_nodes,
                "recurse_types": recurse_types or ["email", "phone", "domain", "linkedin_url", "username"],
            }
            return plan

        recurse_types_set = set(recurse_types or ["email", "phone", "domain", "linkedin_url", "username"])

        def canonicalize(t: str, v: str) -> str:
            if v is None:
                return f"{t}:"
            raw = str(v).strip()
            if t == "email":
                return f"email:{raw.lower()}"
            if t == "phone":
                return f"phone:{_normalize_phone(raw)}"
            if t == "domain":
                dom = raw.lower()
                if dom.startswith("www."):
                    dom = dom[4:]
                return f"domain:{dom}"
            if t == "linkedin_url":
                return f"linkedin_url:{normalize_linkedin_url(raw)}"
            if t == "linkedin_username":
                return f"linkedin_username:{normalize_linkedin_username(raw).lower()}"
            if t == "username":
                return f"username:{raw.lower()}"
            if t in {"person", "company"}:
                return f"{t}:{raw.lower()}"
            return f"{t}:{raw}"

        def node_type_for(t: str) -> str:
            if t in {"linkedin_url", "linkedin_username"}:
                return "linkedin"
            return t

        from country_graph_adapter import GraphNode, GraphEdge, GraphResult, CountryGraphAdapter

        graph = GraphResult(
            source_system="io_cli_recursive",
            jurisdiction=jurisdiction or "",
            query=f"{entity_type}:{value}",
        )
        adapter = CountryGraphAdapter(project_id=persist_project) if persist_project else CountryGraphAdapter()

        node_id_by_key: Dict[str, str] = {}
        edge_ids: set[str] = set()

        def ensure_node(t: str, v: str, depth: int) -> str:
            key = canonicalize(t, v)
            if key in node_id_by_key:
                return node_id_by_key[key]
            ntype = node_type_for(t)
            node_id = adapter._generate_node_id(ntype, v, jurisdiction or "")
            node = GraphNode(
                node_id=node_id,
                node_type=ntype,
                label=v,
                properties={
                    "entity_type": t,
                    "value": v,
                    "depth": depth,
                },
                jurisdiction=jurisdiction or "",
                source_system="io_cli",
                source_url="",
                confidence=1.0,
            )
            graph.nodes.append(node)
            node_id_by_key[key] = node_id
            return node_id

        def add_edge(parent_id: str, child_id: str, via: str = ""):
            edge_id = adapter._generate_edge_id("pivot", parent_id, child_id)
            if edge_id in edge_ids:
                return
            edge_ids.add(edge_id)
            graph.edges.append(
                GraphEdge(
                    edge_id=edge_id,
                    edge_type="pivot",
                    source_node_id=parent_id,
                    target_node_id=child_id,
                    properties={"via": via} if via else {},
                    source_system="io_cli",
                    source_url="",
                    confidence=1.0,
                )
            )

        root_id = ensure_node(entity_type, value, depth=0)

        queue = deque([(entity_type, value, jurisdiction, 0, None)])
        visited: set[str] = set()
        executions: List[Dict[str, Any]] = []
        results_by_node: Dict[str, Any] = {}

        while queue and len(executions) < max_nodes:
            etype, val, jur, depth, parent_node_id = queue.popleft()
            key = canonicalize(etype, val)
            if key in visited:
                continue
            visited.add(key)

            node_id = ensure_node(etype, val, depth=depth)
            if parent_node_id:
                add_edge(parent_node_id, node_id)

            try:
                node_result = await self.execute(etype, val, jur)
                status = "ok" if not node_result.get("errors") else "partial"
            except Exception as e:
                node_result = {"error": str(e), "entity_type": etype, "value": val, "jurisdiction": jur}
                status = "error"

            executions.append(
                {"entity_type": etype, "value": val, "jurisdiction": jur, "depth": depth, "status": status}
            )
            results_by_node[node_id] = node_result

            if depth >= max_depth:
                continue

            pivots = _extract_pivot_entities(node_result)
            for pivot_type, pivot_values in pivots.items():
                if pivot_type not in recurse_types_set:
                    continue
                for pv in pivot_values:
                    next_type = pivot_type
                    next_val = pv
                    if next_type == "linkedin_url":
                        next_val = normalize_linkedin_url(next_val)
                    if next_type == "linkedin_username":
                        next_val = normalize_linkedin_username(next_val)

                    next_key = canonicalize(next_type, next_val)
                    if next_key in visited:
                        continue

                    child_id = ensure_node(next_type, next_val, depth=depth + 1)
                    add_edge(node_id, child_id, via=next_type)
                    queue.append((next_type, next_val, jur, depth + 1, node_id))

        frontier = []
        for etype, val, jur, depth, parent_node_id in list(queue):
            frontier.append({"entity_type": etype, "value": val, "jurisdiction": jur, "depth": depth})

        persistence = None
        persistence_error = None
        if persist_project:
            try:
                persistence = await adapter.persist_to_elastic(graph, project_id=persist_project)
            except Exception as e:
                persistence_error = str(e)

        return {
            "entity_type": entity_type,
            "value": value,
            "jurisdiction": jurisdiction,
            "routing": "recursive",
            "recurse": {
                "max_depth": max_depth,
                "max_nodes": max_nodes,
                "recurse_types": sorted(recurse_types_set),
                "executed": executions,
                "executed_count": len(executions),
                "frontier": frontier,
                "frontier_count": len(frontier),
            },
            "graph": graph.to_dict(),
            "persistence": persistence,
            "persistence_error": persistence_error,
            "results_by_node": results_by_node,
            "root_node_id": root_id,
        }

    async def execute_legacy(self, entity_type: str, value: str, jurisdiction: str = None) -> Dict[str, Any]:
        """Legacy execution with hardcoded module calls (kept for compatibility).

        Use execute() for config-driven routing. This method is preserved for
        debugging and fallback purposes.
        """
        self._lazy_load_modules()

        start_time = datetime.now()

        if self.dry_run:
            return self._dry_run_plan(entity_type, value, jurisdiction)

        result = {
            "entity_type": entity_type,
            "value": value,
            "jurisdiction": jurisdiction,
            "timestamp": start_time.isoformat(),
            "modules_run": [],
            "results": {},
            "errors": [],
            "routing": "legacy"
        }

        # Inject test flag for Reality Engine verification if value contains special trigger
        if "test_event_physics" in value:
            result["test_event_mode"] = True

        try:
            # Try reactive cookbook-based execution for company/person DD when:
            # 1. Reactive mode enabled via IO_REACTIVE_MODE=true, OR
            # 2. Jurisdiction provided and CookbookExecutor available
            use_reactive = (
                entity_type in ('company', 'person') and
                jurisdiction and
                COOKBOOK_EXECUTOR_AVAILABLE and
                (self._use_reactive_mode or os.environ.get('IO_COOKBOOK_DD', 'false').lower() == 'true')
            )

            if use_reactive:
                # Use reactive slot-based execution from EDITH cookbooks
                reactive_result = await self._execute_reactive(entity_type, value, jurisdiction)
                if not reactive_result.get("fallback"):
                    # Success - merge reactive result into main result
                    result["routing"] = "reactive_cookbook"
                    result["results"]["cookbook"] = reactive_result
                    result["modules_run"].append("CookbookExecutor")
                    # Also run legacy modules to supplement
                    if entity_type == 'company':
                        await self._company_investigation(value, jurisdiction, result)
                    elif entity_type == 'person':
                        await self._person_investigation(value, jurisdiction, result)
                else:
                    # Fallback to legacy
                    logger.warning(f"Reactive execution failed, falling back to legacy: {reactive_result.get('error')}")
                    if entity_type == 'person':
                        await self._person_investigation(value, jurisdiction, result)
                    elif entity_type == 'company':
                        await self._company_investigation(value, jurisdiction, result)
            elif entity_type == 'person':
                await self._person_investigation(value, jurisdiction, result)
            elif entity_type == 'company':
                await self._company_investigation(value, jurisdiction, result)
            elif entity_type == 'email':
                await self._email_investigation(value, result)
            elif entity_type == 'phone':
                await self._phone_investigation(value, result)
            elif entity_type == 'domain':
                await self._domain_investigation(value, result)
            elif entity_type == 'brand':
                await self._brand_investigation(value, jurisdiction, result)
            elif entity_type == 'product':
                await self._product_investigation(value, jurisdiction, result)
            elif entity_type == 'social_media':
                await self._social_media_investigation(value, result)
            else:
                result["errors"].append(f"Unknown entity type: {entity_type}")

            # RUN REALITY ENGINE
            result["reality_check"] = await self._run_reality_check(result)

        except Exception as e:
            result["errors"].append(f"Pipeline error: {str(e)}")

        result["duration_seconds"] = (datetime.now() - start_time).total_seconds()
        return result

    def _dry_run_plan(self, entity_type: str, value: str, jurisdiction: str = None) -> Dict[str, Any]:
        """Show what would execute without actually running.

        Uses ConfigDrivenRouter to show all sources that would be queried.
        If SASTRE is available, also includes InvestigationPlanner for dynamic,
        jurisdiction-aware plans based on flows.json data.
        """
        geo_note = f" (geo filter: {jurisdiction})" if jurisdiction else ""
        brightdata_note = "✓" if getattr(self, '_brightdata_available', False) else "⚠️ API key not set"

        # Get config-driven sources
        config_router = ConfigDrivenRouter()
        sources = config_router.get_sources_for_input(entity_type, jurisdiction)

        config_driven_plan = []
        for i, source in enumerate(sources):
            if source["type"] == "elasticsearch":
                config_driven_plan.append(f"{i+1}. [ES] {source['index']} (cluster: {source.get('cluster', 'unknown')})")
            elif source["type"] == "module":
                mod = source.get("module", "unknown")
                method = source.get("method") or source.get("function", "unknown")
                config_driven_plan.append(f"{i+1}. [MODULE] {mod}.{method}")

        if entity_type == "social_media":
            config_driven_plan = ["1. [MODULE] BRUTE-social_media (ToS-safe link generation)"]

        # Try SASTRE InvestigationPlanner for jurisdiction-aware planning
        sastre_plan = None
        if SASTRE_AVAILABLE and jurisdiction:
            try:
                planner = InvestigationPlanner()
                plan = planner.create_plan(
                    entity_type=entity_type,
                    entity_name=value,
                    jurisdiction=jurisdiction,
                )
                if plan.steps:
                    sastre_plan = {
                        "jurisdiction_routes": [
                            f"{i+1}. {s.source_label} [{s.tier.value}] → {', '.join(s.output_columns[:3])}"
                            for i, s in enumerate(plan.steps[:8])
                        ],
                        "total_steps": len(plan.steps),
                        "ku_quadrant": plan.ku_quadrant.value,
                        "estimated_completeness": f"{plan.estimated_completeness:.0%}",
                    }

                    # Also generate query variations
                    generator = QueryGenerator()
                    query = generator.generate_for_entity(value, entity_type)
                    sastre_plan["query_variations"] = query.variations[:5]
                    sastre_plan["free_ors"] = query.free_ors[:200] + "..." if len(query.free_ors) > 200 else query.free_ors
            except Exception as e:
                sastre_plan = {"error": str(e)}

        # Fallback static plans
        plans = {
            'person': [
                "1. EYE-D OSINT lookup (social profiles, breach data)",
                f"2. WDC Person entities (6.8M indexed){geo_note} → name, email, phone, job_title + works_for edge",
                "3. OpenSanctions check (PEP/sanctions screening)",
                "4. LINKLATER web enrichment (news, mentions)",
                "5. Index to Elasticsearch (cymonides-1)"
            ],
            'company': [
                f"1. Torpedo country registry{geo_note} → full profile from national registry (if jurisdiction provided)",
                "2. Corporella registry lookup (corporate records)",
                f"3. WDC Organization entities (9.6M indexed){geo_note} → name, email, phone, address, taxID, vatID",
                f"4. WDC LocalBusiness entities (478K indexed){geo_note} → for retail/service businesses",
                "5. OpenCorporates search (global company data)",
                "6. OpenSanctions check (sanctions screening)",
                "7. Index to Elasticsearch (cymonides-1)"
            ],
            'email': [
                "1. EYE-D reverse lookup (associated profiles)",
                "2. WDC email search (across all entity types) → name, phone, address + works_for edge",
                "3. Breach database check (DeHashed/HIBP)",
                "4. Domain extraction → domain investigation",
                "5. Index to Elasticsearch (cymonides-1)"
            ],
            'phone': [
                "1. EYE-D reverse lookup (owner info)",
                "2. WDC phone search (across all entity types) → owner name, email, address",
                "3. Carrier/number info lookup",
                "4. Index to Elasticsearch (cymonides-1)"
            ],
            'domain': [
                "1. WHOIS lookup (registrant info)",
                f"2. WDC entities on domain{geo_note} → all Schema.org entities from this domain",
                "3. LINKLATER Backlinks (CC Web Graph 421M edges + Majestic)",
                "4. LINKLATER GA Tracker → related domains via shared analytics codes",
                f"5. BrightData scrape [{brightdata_note}] → homepage content extraction (bypasses bot detection)",
                "6. Index to Elasticsearch (cymonides-1)"
            ],
            'username': [
                "1. EYE-D Sherlock username search",
                "2. Breach database lookup (breach_records)",
                "3. Social link expansion (social: u:<username>)",
                "4. Index to Elasticsearch (cymonides-1)"
            ],
            'linkedin_url': [
                "1. LinkedIn indices lookup (linkedin_unified, affiliate_linkedin_companies)",
                "2. Person enrichment (persons_unified)",
                "3. Social link expansion (social: li:<slug>)",
                "4. Index to Elasticsearch (cymonides-1)"
            ],
            'social_media': [
                "1. BRUTE social_media link set (ToS-safe)",
                "2. Pivot discovered profiles back into IO (optional)",
                "3. Index to Elasticsearch (cymonides-1)"
            ],
            'brand': [
                f"1. WDC Product entities by brand (20.4M indexed){geo_note} → products, prices, availability",
                "2. WDC Organization search (parent company)",
                "3. OpenCorporates trademark/company search",
                "4. Index to Elasticsearch (cymonides-1)"
            ],
            'product': [
                f"1. WDC Product entities (20.4M indexed){geo_note} → name, brand, price, sku, gtin",
                "2. WDC Organization search (manufacturer)",
                "3. Index to Elasticsearch (cymonides-1)"
            ]
        }

        result = {
            "dry_run": True,
            "entity_type": entity_type,
            "value": value,
            "jurisdiction": jurisdiction,
            "config_driven_sources": config_driven_plan,  # Sources from IO_INTEGRATION.json
            "legacy_plan": plans.get(entity_type, ["Unknown entity type"]),  # Legacy static plan
            "note": "Use without --dry-run to execute. Execution uses config-driven routing."
        }

        # Add SASTRE plan if available
        if sastre_plan:
            result["sastre_plan"] = sastre_plan

        return result

    async def _person_investigation(self, name: str, jurisdiction: str, result: Dict):
        """Full person investigation pipeline."""
        # 1. EYE-D OSINT
        if self._eye_d:
            try:
                result["modules_run"].append("EYE-D")
                osint = self._eye_d()
                eye_d_result = await self._run_eye_d_person(osint, name)
                result["results"]["eye_d"] = eye_d_result
            except Exception as e:
                result["errors"].append(f"EYE-D error: {str(e)}")
        else:
            result["errors"].append("EYE-D module not available")

        # 2. WDC Person entities (6.8M indexed)
        if hasattr(self, '_wdc_search_person') and self._wdc_search_person:
            try:
                result["modules_run"].append("WDC")
                # Map jurisdiction to geo TLD filter
                geo = jurisdiction.lower() if jurisdiction else None
                wdc_results = self._wdc_search_person(name=name, geo=geo, limit=50)
                # Results contain: name, email, telephone, jobTitle, worksFor, address, url, domain
                result["results"]["schema_org_entities"] = wdc_results
            except Exception as e:
                result["errors"].append(f"WDC Person search error: {str(e)}")

        # 3. Sanctions check
        try:
            result["modules_run"].append("OpenSanctions")
            sanctions_result = await self._check_sanctions(name, 'person')
            result["results"]["sanctions"] = sanctions_result
        except Exception as e:
            result["errors"].append(f"Sanctions check error: {str(e)}")

        # 4. Web enrichment (placeholder for LINKLATER)
        result["modules_run"].append("WebEnrichment")
        result["results"]["web_enrichment"] = {"status": "pending", "note": "LINKLATER integration"}

        # 6. DYNAMIC RULE EXECUTION - Run matching rules from rules.json
        # This executes ALL rules that take person_name (code 7) as input
        try:
            result["modules_run"].append("DynamicRules")
            # person_name = field code 7
            rules_result = await self.execute_matching_rules(
                input_code=7,
                value=name,
                jurisdiction=jurisdiction,
                limit=20  # Top 20 matching rules
            )
            result["results"]["dynamic_rules"] = {
                "rules_matched": rules_result.get("rules_matched", 0),
                "rules_succeeded": rules_result.get("rules_succeeded", 0),
                "results": rules_result.get("results", [])
            }
        except Exception as e:
            result["errors"].append(f"Dynamic rules error: {str(e)}")

        # 7. OUTPUT CODE MAPPING - Map all results to I/O Matrix field codes
        if OUTPUT_MAPPER_AVAILABLE:
            try:
                if "output_codes" not in result:
                    result["output_codes"] = []
                if "mapped_nodes" not in result:
                    result["mapped_nodes"] = []
                if "mapped_edges" not in result:
                    result["mapped_edges"] = []

                mapper = get_mapper()

                # Map EYE-D result
                if result["results"].get("eye_d"):
                    eye_d_result = result["results"]["eye_d"]
                    mapped = mapper.map_eyed_result(eye_d_result, name, "person")
                    result["output_codes"].extend(mapped.output_codes)
                    result["mapped_nodes"].extend([e.to_dict() for e in mapped.nodes])
                    result["mapped_edges"].extend([e.to_dict() for e in mapped.edges])

                # Map WDC/Schema.org results
                if result["results"].get("schema_org_entities"):
                    for entity in result["results"]["schema_org_entities"]:
                        entity_dict = {
                            "entity_type": "person",
                            "entity_code": FIELD_CODES.get("person_name", 7),
                            "value": entity.get("name"),
                            "source_module": "wdc_schema_org",
                            "properties": {
                                "email": entity.get("email"),
                                "phone": entity.get("telephone"),
                                "job_title": entity.get("jobTitle"),
                                "works_for": entity.get("worksFor"),
                                "address": entity.get("address"),
                                "url": entity.get("url"),
                                "domain": entity.get("domain"),
                            }
                        }
                        result["mapped_nodes"].append(entity_dict)

                # Map sanctions result
                if result["results"].get("sanctions"):
                    sanctions_result = result["results"]["sanctions"]
                    mapped = mapper.map_sanctions_result(sanctions_result, name, "person")
                    result["output_codes"].extend(mapped.output_codes)
                    result["mapped_nodes"].extend([e.to_dict() for e in mapped.nodes])
                    result["mapped_edges"].extend([e.to_dict() for e in mapped.edges])

                # Deduplicate output codes
                result["output_codes"] = list(set(result["output_codes"]))

            except Exception as e:
                result["errors"].append(f"Output mapping error: {str(e)}")

    async def _company_investigation(self, company_name: str, jurisdiction: str, result: Dict):
        """Full company investigation pipeline."""
        geo = jurisdiction.lower() if jurisdiction else None

        # 1. Torpedo - Country-specific registry lookup (when jurisdiction provided)
        if jurisdiction and self._torpedo:
            try:
                result["modules_run"].append("Torpedo")
                torpedo = self._torpedo()
                await torpedo.load_sources()
                torpedo_result = await torpedo.fetch_profile(company_name, jurisdiction.upper())
                result["results"]["registry_profile"] = torpedo_result
            except Exception as e:
                result["errors"].append(f"Torpedo error: {str(e)}")

        # 2. Corporella
        if self._corporella:
            try:
                result["modules_run"].append("Corporella")
                corp = self._corporella()
                corp_result = await corp.search_company(company_name, max_results=10)
                result["results"]["corporella"] = corp_result
            except Exception as e:
                result["errors"].append(f"Corporella error: {str(e)}")

        # 3. WDC Organization entities (9.6M indexed)
        if hasattr(self, '_wdc_search_org') and self._wdc_search_org:
            try:
                result["modules_run"].append("WDC-Org")
                org_results = self._wdc_search_org(name=company_name, geo=geo, limit=50)
                # Results contain: name, email, telephone, address, taxID, vatID, url, domain
                result["results"]["schema_org_organizations"] = org_results
            except Exception as e:
                result["errors"].append(f"WDC Organization search error: {str(e)}")

        # 4. WDC LocalBusiness entities (478K indexed) - for retail/service businesses
        if hasattr(self, '_wdc_search_local') and self._wdc_search_local:
            try:
                result["modules_run"].append("WDC-LocalBiz")
                local_results = self._wdc_search_local(name=company_name, geo=geo, limit=30)
                # Results contain: name, email, telephone, address, priceRange, openingHours, url, domain
                result["results"]["schema_org_local_businesses"] = local_results
            except Exception as e:
                result["errors"].append(f"WDC LocalBusiness search error: {str(e)}")

        # 5. CYMONIDES Elasticsearch indices - company_name → domain/website
        try:
            from elasticsearch import Elasticsearch
            es_url = os.environ.get('ELASTICSEARCH_URL', 'http://localhost:9200')
            es = Elasticsearch([es_url])

            # 5a. unified_domain_profiles - company_name → domain (5.8M records)
            try:
                result["modules_run"].append("CYMONIDES-DomainProfiles")
                domain_res = es.search(
                    index="unified_domain_profiles",
                    body={
                        "query": {"match": {"company_name": {"query": company_name, "fuzziness": "AUTO"}}},
                        "size": 20,
                        "_source": ["domain", "company_name", "technologies", "industry"]
                    }
                )
                result["results"]["domain_profiles"] = [h["_source"] for h in domain_res.get("hits", {}).get("hits", [])]
            except Exception as e:
                result["errors"].append(f"CYMONIDES domain_profiles: {str(e)}")

            # 5b. affiliate_linkedin_companies - company_name → linkedin (2.8M records)
            try:
                result["modules_run"].append("CYMONIDES-LinkedIn")
                linkedin_res = es.search(
                    index="affiliate_linkedin_companies",
                    body={
                        "query": {"match": {"name": {"query": company_name, "fuzziness": "AUTO"}}},
                        "size": 10,
                        "_source": ["name", "linkedin_url", "industry", "employee_count", "headquarters"]
                    }
                )
                result["results"]["linkedin_companies"] = [h["_source"] for h in linkedin_res.get("hits", {}).get("hits", [])]
            except Exception as e:
                result["errors"].append(f"CYMONIDES linkedin: {str(e)}")

            # 5c. companies_unified - full company records (3.1M records)
            try:
                result["modules_run"].append("CYMONIDES-CompaniesUnified")
                companies_res = es.search(
                    index="companies_unified",
                    body={
                        "query": {"bool": {
                            "should": [
                                {"match": {"name": {"query": company_name, "boost": 3}}},
                                {"match": {"name_normalized": {"query": company_name, "boost": 2}}}
                            ],
                            "filter": [{"term": {"jurisdiction": jurisdiction.upper()}}] if jurisdiction else []
                        }},
                        "size": 10,
                        "_source": ["name", "company_number", "jurisdiction", "status", "address", "officers", "incorporation_date"]
                    }
                )
                result["results"]["companies_unified"] = [h["_source"] for h in companies_res.get("hits", {}).get("hits", [])]
            except Exception as e:
                result["errors"].append(f"CYMONIDES companies_unified: {str(e)}")

            # 5d. openownership - beneficial ownership (21M+ records)
            try:
                result["modules_run"].append("CYMONIDES-OpenOwnership")
                ownership_res = es.search(
                    index="openownership",
                    body={
                        "query": {"bool": {
                            "must": [{"match": {"name": {"query": company_name, "fuzziness": "AUTO"}}}],
                            "filter": [{"term": {"entity_type": "registeredEntity"}}]
                        }},
                        "size": 20,
                        "_source": ["name", "company_number", "jurisdiction", "country", "address", "statement_type"]
                    }
                )
                result["results"]["beneficial_ownership"] = [h["_source"] for h in ownership_res.get("hits", {}).get("hits", [])]
            except Exception as e:
                result["errors"].append(f"CYMONIDES openownership: {str(e)}")

        except ImportError:
            result["errors"].append("elasticsearch package not installed")
        except Exception as e:
            result["errors"].append(f"CYMONIDES ES error: {str(e)}")

        # 6. OpenCorporates (if available)
        try:
            result["modules_run"].append("OpenCorporates")
            oc_result = await self._search_opencorporates(company_name, jurisdiction)
            result["results"]["opencorporates"] = oc_result
        except Exception as e:
            result["errors"].append(f"OpenCorporates error: {str(e)}")

        # 7. Sanctions check
        try:
            result["modules_run"].append("OpenSanctions")
            sanctions_result = await self._check_sanctions(company_name, 'company')
            result["results"]["sanctions"] = sanctions_result
        except Exception as e:
            result["errors"].append(f"Sanctions check error: {str(e)}")

        # 8. OCCRP Aleph - 237 collections with jurisdiction-aware routing
        if self._aleph:
            try:
                result["modules_run"].append("OCCRP-Aleph")
                aleph_result = await self._search_aleph(company_name, jurisdiction, entity_type='company')
                result["results"]["aleph"] = aleph_result
            except Exception as e:
                result["errors"].append(f"OCCRP Aleph error: {str(e)}")

        # 9. DYNAMIC RULE EXECUTION - Run matching rules from rules.json
        # This executes ALL rules that take company_name (code 13) as input
        try:
            result["modules_run"].append("DynamicRules")
            # company_name = field code 13
            rules_result = await self.execute_matching_rules(
                input_code=13,
                value=company_name,
                jurisdiction=jurisdiction,
                limit=20  # Top 20 matching rules
            )
            result["results"]["dynamic_rules"] = {
                "rules_matched": rules_result.get("rules_matched", 0),
                "rules_succeeded": rules_result.get("rules_succeeded", 0),
                "results": rules_result.get("results", [])
            }
        except Exception as e:
            result["errors"].append(f"Dynamic rules error: {str(e)}")

        # 10. OUTPUT CODE MAPPING - Map all results to I/O Matrix field codes
        if OUTPUT_MAPPER_AVAILABLE:
            try:
                if "output_codes" not in result:
                    result["output_codes"] = []
                if "mapped_nodes" not in result:
                    result["mapped_nodes"] = []
                if "mapped_edges" not in result:
                    result["mapped_edges"] = []

                mapper = get_mapper()

                # Map Corporella result
                if result["results"].get("corporella"):
                    corp_result = result["results"]["corporella"]
                    mapped = mapper.map_corporella_result(corp_result, company_name, jurisdiction)
                    result["output_codes"].extend(mapped.output_codes)
                    result["mapped_nodes"].extend([e.to_dict() for e in mapped.nodes])
                    result["mapped_edges"].extend([e.to_dict() for e in mapped.edges])

                # Map OpenCorporates result (similar structure to Corporella)
                if result["results"].get("opencorporates"):
                    oc_result = result["results"]["opencorporates"]
                    if isinstance(oc_result, dict) and oc_result.get("results"):
                        for company_rec in oc_result.get("results", [])[:5]:
                            mapped = mapper.map_corporella_result(company_rec, company_name, jurisdiction)
                            result["output_codes"].extend(mapped.output_codes)
                            result["mapped_nodes"].extend([e.to_dict() for e in mapped.nodes])
                            result["mapped_edges"].extend([e.to_dict() for e in mapped.edges])

                # Map sanctions result
                if result["results"].get("sanctions"):
                    sanctions_result = result["results"]["sanctions"]
                    mapped = mapper.map_sanctions_result(sanctions_result, company_name, "company")
                    result["output_codes"].extend(mapped.output_codes)
                    result["mapped_nodes"].extend([e.to_dict() for e in mapped.nodes])
                    result["mapped_edges"].extend([e.to_dict() for e in mapped.edges])

                # Map beneficial ownership result
                if result["results"].get("beneficial_ownership"):
                    for bo_rec in result["results"]["beneficial_ownership"]:
                        # Extract person entities from ownership records
                        if bo_rec.get("name"):
                            entity_dict = {
                                "entity_type": "company",
                                "entity_code": FIELD_CODES.get("company_name", 13),
                                "value": bo_rec.get("name"),
                                "source_module": "cymonides_openownership",
                                "properties": {
                                    "company_number": bo_rec.get("company_number"),
                                    "jurisdiction": bo_rec.get("jurisdiction"),
                                    "country": bo_rec.get("country"),
                                }
                            }
                            result["mapped_nodes"].append(entity_dict)
                            result["output_codes"].append(FIELD_CODES.get("company_beneficial_owners", 58))

                # Deduplicate output codes
                result["output_codes"] = list(set(result["output_codes"]))

            except Exception as e:
                result["errors"].append(f"Output mapping error: {str(e)}")

    async def _email_investigation(self, email: str, result: Dict):
        """Full email investigation pipeline."""
        # 1. EYE-D reverse lookup
        if self._eye_d:
            try:
                result["modules_run"].append("EYE-D")
                osint = self._eye_d()
                eye_d_result = await self._run_eye_d_email(osint, email)
                result["results"]["eye_d"] = eye_d_result

                # 1.5 Extract Facebook IDs from OSINT Industries results and scrape profiles
                # When OSINT Industries returns a Facebook user ID, we can access the profile
                # using: https://www.facebook.com/profile.php?id={numeric_id}
                facebook_ids = self._extract_facebook_ids_from_eye_d(eye_d_result)
                if facebook_ids:
                    result["modules_run"].append("Facebook-BrightData")
                    facebook_profiles = []
                    for fb_info in facebook_ids:
                        try:
                            profile_data = await self._scrape_facebook_profile(
                                fb_info['facebook_id'],
                                fb_info['profile_url']
                            )
                            facebook_profiles.append({
                                **fb_info,
                                'scrape_result': profile_data
                            })
                        except Exception as fb_err:
                            facebook_profiles.append({
                                **fb_info,
                                'scrape_result': {
                                    'status': 'error',
                                    'error': str(fb_err)
                                }
                            })
                    result["results"]["facebook_profiles"] = facebook_profiles
                    result["results"]["facebook_ids_found"] = len(facebook_ids)
            except Exception as e:
                result["errors"].append(f"EYE-D error: {str(e)}")

        # 2. WDC email search (across Person, Organization, LocalBusiness entities)
        if hasattr(self, '_wdc') and self._wdc:
            try:
                result["modules_run"].append("WDC")
                wdc_service = self._wdc()
                wdc_results = wdc_service.search_by_email(email, exact=True)
                # Results contain: name, phone, address, url, domain + works_for edge to company
                result["results"]["schema_org_entities"] = wdc_results
            except Exception as e:
                result["errors"].append(f"WDC email search error: {str(e)}")

        # 3. Extract domain and queue domain investigation
        domain = email.split('@')[-1] if '@' in email else None
        if domain:
            result["results"]["extracted_domain"] = domain
            result["results"]["domain_investigation"] = {"status": "queued", "domain": domain}

        # 4. DYNAMIC RULE EXECUTION - Run matching rules from rules.json
        # email = field code 1
        try:
            result["modules_run"].append("DynamicRules")
            rules_result = await self.execute_matching_rules(
                input_code=1,
                value=email,
                jurisdiction=None,
                limit=15
            )
            result["results"]["dynamic_rules"] = {
                "rules_matched": rules_result.get("rules_matched", 0),
                "rules_succeeded": rules_result.get("rules_succeeded", 0),
                "results": rules_result.get("results", [])
            }
        except Exception as e:
            result["errors"].append(f"Dynamic rules error: {str(e)}")

        # 5. OUTPUT CODE MAPPING - Map EYE-D results to I/O Matrix field codes
        if OUTPUT_MAPPER_AVAILABLE:
            try:
                if "output_codes" not in result:
                    result["output_codes"] = []
                if "mapped_nodes" not in result:
                    result["mapped_nodes"] = []
                if "mapped_edges" not in result:
                    result["mapped_edges"] = []

                mapper = get_mapper()

                # Map EYE-D result
                if result["results"].get("eye_d"):
                    eye_d_result = result["results"]["eye_d"]
                    mapped = mapper.map_eyed_result(eye_d_result, email, "email")
                    result["output_codes"].extend(mapped.output_codes)
                    result["mapped_nodes"].extend([e.to_dict() for e in mapped.nodes])
                    result["mapped_edges"].extend([e.to_dict() for e in mapped.edges])

                # Map WDC/Schema.org results
                if result["results"].get("schema_org_entities"):
                    for entity in result["results"]["schema_org_entities"]:
                        entity_dict = {
                            "entity_type": entity.get("type", "unknown"),
                            "entity_code": FIELD_CODES.get(entity.get("type"), 0),
                            "value": entity.get("name"),
                            "source_module": "wdc_schema_org",
                            "properties": {
                                "email": entity.get("email"),
                                "phone": entity.get("telephone"),
                                "address": entity.get("address"),
                                "url": entity.get("url"),
                                "domain": entity.get("domain"),
                            }
                        }
                        result["mapped_nodes"].append(entity_dict)

                # Deduplicate output codes
                result["output_codes"] = list(set(result["output_codes"]))

            except Exception as e:
                result["errors"].append(f"Output mapping error: {str(e)}")

    async def _phone_investigation(self, phone: str, result: Dict):
        """Full phone investigation pipeline."""
        # 1. EYE-D reverse lookup
        if self._eye_d:
            try:
                result["modules_run"].append("EYE-D")
                osint = self._eye_d()
                eye_d_result = await self._run_eye_d_phone(osint, phone)
                result["results"]["eye_d"] = eye_d_result

                # 1.5 Extract Facebook IDs from OSINT Industries results and scrape profiles
                facebook_ids = self._extract_facebook_ids_from_eye_d(eye_d_result)
                if facebook_ids:
                    result["modules_run"].append("Facebook-BrightData")
                    facebook_profiles = []
                    for fb_info in facebook_ids:
                        try:
                            profile_data = await self._scrape_facebook_profile(
                                fb_info['facebook_id'],
                                fb_info['profile_url']
                            )
                            facebook_profiles.append({
                                **fb_info,
                                'scrape_result': profile_data
                            })
                        except Exception as fb_err:
                            facebook_profiles.append({
                                **fb_info,
                                'scrape_result': {
                                    'status': 'error',
                                    'error': str(fb_err)
                                }
                            })
                    result["results"]["facebook_profiles"] = facebook_profiles
                    result["results"]["facebook_ids_found"] = len(facebook_ids)
            except Exception as e:
                result["errors"].append(f"EYE-D error: {str(e)}")

        # 2. WDC phone search (across Person, Organization, LocalBusiness entities)
        if hasattr(self, '_wdc') and self._wdc:
            try:
                result["modules_run"].append("WDC")
                wdc_service = self._wdc()
                wdc_results = wdc_service.search_by_phone(phone)
                # Results contain: name, email, address, url, domain + works_for edge to company
                result["results"]["schema_org_entities"] = wdc_results
            except Exception as e:
                result["errors"].append(f"WDC phone search error: {str(e)}")

        # 3. DYNAMIC RULE EXECUTION - Run matching rules from rules.json
        # phone = field code 2
        try:
            result["modules_run"].append("DynamicRules")
            rules_result = await self.execute_matching_rules(
                input_code=2,
                value=phone,
                jurisdiction=None,
                limit=15
            )
            result["results"]["dynamic_rules"] = {
                "rules_matched": rules_result.get("rules_matched", 0),
                "rules_succeeded": rules_result.get("rules_succeeded", 0),
                "results": rules_result.get("results", [])
            }
        except Exception as e:
            result["errors"].append(f"Dynamic rules error: {str(e)}")

        # 4. OUTPUT CODE MAPPING - Map EYE-D results to I/O Matrix field codes
        if OUTPUT_MAPPER_AVAILABLE:
            try:
                if "output_codes" not in result:
                    result["output_codes"] = []
                if "mapped_nodes" not in result:
                    result["mapped_nodes"] = []
                if "mapped_edges" not in result:
                    result["mapped_edges"] = []

                mapper = get_mapper()

                # Map EYE-D result
                if result["results"].get("eye_d"):
                    eye_d_result = result["results"]["eye_d"]
                    mapped = mapper.map_eyed_result(eye_d_result, phone, "phone")
                    result["output_codes"].extend(mapped.output_codes)
                    result["mapped_nodes"].extend([e.to_dict() for e in mapped.nodes])
                    result["mapped_edges"].extend([e.to_dict() for e in mapped.edges])

                # Map WDC/Schema.org results
                if result["results"].get("schema_org_entities"):
                    for entity in result["results"]["schema_org_entities"]:
                        entity_dict = {
                            "entity_type": entity.get("type", "unknown"),
                            "entity_code": FIELD_CODES.get(entity.get("type"), 0),
                            "value": entity.get("name"),
                            "source_module": "wdc_schema_org",
                            "properties": {
                                "email": entity.get("email"),
                                "phone": entity.get("telephone"),
                                "address": entity.get("address"),
                                "url": entity.get("url"),
                                "domain": entity.get("domain"),
                            }
                        }
                        result["mapped_nodes"].append(entity_dict)

                # Deduplicate output codes
                result["output_codes"] = list(set(result["output_codes"]))

            except Exception as e:
                result["errors"].append(f"Output mapping error: {str(e)}")

    async def _domain_investigation(self, domain: str, result: Dict):
        """Full domain investigation pipeline."""
        # Clean domain
        if domain.startswith('http://') or domain.startswith('https://'):
            from urllib.parse import urlparse
            domain = urlparse(domain).netloc

        result["results"]["domain"] = domain

        # Initialize output codes tracking
        if "output_codes" not in result:
            result["output_codes"] = []
        if "mapped_nodes" not in result:
            result["mapped_nodes"] = []
        if "mapped_edges" not in result:
            result["mapped_edges"] = []

        # 1. WHOIS lookup (HISTORIC by default)
        try:
            result["modules_run"].append("WHOIS")
            whois_result = await self._whois_lookup(domain)
            result["results"]["whois"] = whois_result

            # Map WHOIS output to field codes
            if OUTPUT_MAPPER_AVAILABLE and whois_result.get("status") == "ok":
                mapper = get_mapper()
                mapped = mapper.map_whois_result(whois_result, domain)
                result["output_codes"].extend(mapped.output_codes)
                result["mapped_nodes"].extend([e.to_dict() for e in mapped.nodes])
                result["mapped_edges"].extend([e.to_dict() for e in mapped.edges])
                result["results"]["whois_mapped"] = mapped.to_dict()
        except Exception as e:
            result["errors"].append(f"WHOIS error: {str(e)}")

        # 2. WDC - find all Schema.org entities on this domain
        if hasattr(self, '_wdc') and self._wdc:
            try:
                result["modules_run"].append("WDC")
                wdc_service = self._wdc()
                wdc_results = wdc_service.find_by_domain(domain)
                # Results contain: all Person, Organization, LocalBusiness, Product entities from this domain
                result["results"]["schema_org_entities"] = wdc_results
            except Exception as e:
                result["errors"].append(f"WDC domain search error: {str(e)}")

        # 3. LINKLATER Backlinks (CC Web Graph + Majestic)
        if self._backlinks:
            try:
                result["modules_run"].append("Backlinks")
                backlink_discovery = self._backlinks()
                # Get referring domains (fast mode)
                backlink_results = await backlink_discovery.get_referring_domains(domain, limit=100)
                result["results"]["backlinks"] = backlink_results
                await backlink_discovery.close()

                # Map backlinks output to field codes
                if OUTPUT_MAPPER_AVAILABLE and backlink_results:
                    mapper = get_mapper()
                    mapped = mapper.map_backlinks_result({"backlinks": backlink_results}, domain)
                    result["output_codes"].extend(mapped.output_codes)
                    result["mapped_nodes"].extend([e.to_dict() for e in mapped.nodes])
                    result["mapped_edges"].extend([e.to_dict() for e in mapped.edges])
            except Exception as e:
                result["errors"].append(f"Backlinks error: {str(e)}")

        # 4. LINKLATER GA Tracker (related domains via shared analytics codes)
        if self._ga_tracker:
            try:
                result["modules_run"].append("GATracker")
                ga_tracker = self._ga_tracker()
                # Discover GA/GTM codes and find related domains
                ga_codes = await ga_tracker.discover_codes(domain)
                related_domains = await ga_tracker.find_related_domains(domain)
                result["results"]["ga_tracker"] = {
                    "codes": ga_codes,
                    "related_domains": related_domains
                }
            except Exception as e:
                result["errors"].append(f"GA Tracker error: {str(e)}")

        # 5. DYNAMIC RULE EXECUTION - Run matching rules from rules.json
        # domain_url = field code 6
        try:
            result["modules_run"].append("DynamicRules")
            rules_result = await self.execute_matching_rules(
                input_code=6,
                value=domain,
                jurisdiction=None,
                limit=20
            )
            result["results"]["dynamic_rules"] = {
                "rules_matched": rules_result.get("rules_matched", 0),
                "rules_succeeded": rules_result.get("rules_succeeded", 0),
                "results": rules_result.get("results", [])
            }
        except Exception as e:
            result["errors"].append(f"Dynamic rules error: {str(e)}")

    async def _brand_investigation(self, brand_name: str, jurisdiction: str, result: Dict):
        """Full brand investigation pipeline - searches products by brand."""
        geo = jurisdiction.lower() if jurisdiction else None

        # 1. WDC Product entities filtered by brand (20.4M indexed)
        if hasattr(self, '_wdc_search_product') and self._wdc_search_product:
            try:
                result["modules_run"].append("WDC-Product")
                product_results = self._wdc_search_product(brand=brand_name, geo=geo, limit=100)
                # Results contain: product name, price, sku, gtin, availability, url, domain
                result["results"]["products"] = product_results
            except Exception as e:
                result["errors"].append(f"WDC Product search error: {str(e)}")

        # 2. WDC Organization search for parent company
        if hasattr(self, '_wdc_search_org') and self._wdc_search_org:
            try:
                result["modules_run"].append("WDC-Org")
                org_results = self._wdc_search_org(name=brand_name, geo=geo, limit=20)
                # Results contain: company name, email, phone, address, taxID, vatID
                result["results"]["parent_company"] = org_results
            except Exception as e:
                result["errors"].append(f"WDC Organization search error: {str(e)}")

        # 3. OpenCorporates search for trademark/company
        try:
            result["modules_run"].append("OpenCorporates")
            oc_result = await self._search_opencorporates(brand_name, jurisdiction)
            result["results"]["opencorporates"] = oc_result
        except Exception as e:
            result["errors"].append(f"OpenCorporates error: {str(e)}")

    async def _product_investigation(self, product_name: str, jurisdiction: str, result: Dict):
        """Full product investigation pipeline."""
        geo = jurisdiction.lower() if jurisdiction else None

        # 1. WDC Product entities (20.4M indexed)
        if hasattr(self, '_wdc_search_product') and self._wdc_search_product:
            try:
                result["modules_run"].append("WDC-Product")
                product_results = self._wdc_search_product(name=product_name, geo=geo, limit=100)
                # Results contain: name, brand, price, sku, gtin, availability, url, domain
                result["results"]["products"] = product_results
            except Exception as e:
                result["errors"].append(f"WDC Product search error: {str(e)}")

        # 2. Try to find manufacturer from product brand
        if hasattr(self, '_wdc_search_org') and self._wdc_search_org:
            try:
                result["modules_run"].append("WDC-Org")
                # Extract brand from product results if available
                brand = result.get("results", {}).get("products", [{}])[0].get("brand") if result.get("results", {}).get("products") else None
                if brand:
                    org_results = self._wdc_search_org(name=brand, geo=geo, limit=10)
                    result["results"]["manufacturer"] = org_results
            except Exception as e:
                result["errors"].append(f"WDC Organization search error: {str(e)}")

    async def _social_media_investigation(self, value: str, result: Dict):
        """Social media investigation - ToS-safe URL generation via BRUTE.

        Accepted formats:
          - "<platform>: <target>" (fb, tw, x, ig, threads, li/linkedin)
          - "social: <query>" / "all: <query>" (multi-platform link set)
        """
        raw_value = (value or "").strip()
        if not raw_value:
            result["errors"].append("Missing social media query.")
            return

        try:
            from brute.targeted_searches.community import social_media as brute_social
        except Exception as e:
            result["errors"].append(f"BRUTE social_media module not available: {e}")
            return

        def _parse_platform(v: str) -> Tuple[str, str]:
            m = re.match(
                r'^(fb|facebook|tw|twitter|x|ig|instagram|threads|li|linkedin|social|all)\s*:\s*(.+)$',
                v,
                re.IGNORECASE,
            )
            if not m:
                return "social", v.strip()
            return m.group(1).lower(), m.group(2).strip()

        platform, target = _parse_platform(raw_value)
        if platform in {"social", "all"}:
            nested_platform, nested_target = _parse_platform(target)
            if nested_platform not in {"social", "all"}:
                platform, target = nested_platform, nested_target

        platform_map = {
            "fb": "facebook",
            "facebook": "facebook",
            "tw": "twitter",
            "twitter": "twitter",
            "x": "twitter",
            "ig": "instagram",
            "instagram": "instagram",
            "threads": "threads",
            "li": "linkedin",
            "linkedin": "linkedin",
            "social": "social",
            "all": "social",
        }
        platform = platform_map.get(platform, platform)

        result["social_platform"] = platform
        result["social_target"] = target
        result["modules_run"].append("BRUTE-social_media")

        links: List[Dict[str, Any]] = []
        if platform == "facebook":
            links = brute_social.fb_results(target)
        elif platform == "twitter":
            candidate = target.lstrip("@")
            username = candidate if re.match(r"^[A-Za-z0-9_]{1,30}$", candidate) else None
            links = brute_social.twitter_results(target, username=username)
        elif platform == "instagram":
            username = target.lstrip("@")
            links = brute_social.instagram_results(username)
        elif platform == "threads":
            username = target.lstrip("@")
            links = [
                r for r in brute_social.instagram_results(username)
                if r.get("search_engine") == "threads" or "Threads" in (r.get("title") or "")
            ]
        elif platform == "linkedin":
            username = None
            url_match = re.search(r'linkedin\.com/(?:in|company)/([^/?#]+)/?', target, re.IGNORECASE)
            if url_match:
                username = url_match.group(1)
            else:
                candidate = target.lstrip("@")
                if re.match(r"^[A-Za-z0-9][A-Za-z0-9-]{2,}$", candidate):
                    username = candidate
            links = brute_social.linkedin_results(target, username=username)
        else:
            username = None
            real_name = None
            if " " in target:
                real_name = target
            elif "/" not in target:
                username = target.lstrip("@")
            links = brute_social.search(target, username=username, real_name=real_name)

        result["results"]["social_links"] = links

    # Helper methods
    async def _run_eye_d_person(self, osint, name: str) -> Dict:
        """Run EYE-D person search."""
        try:
            # Check if method exists
            if hasattr(osint, 'search_person'):
                return await osint.search_person(name)
            elif hasattr(osint, 'search_people'):
                return await osint.search_people(name)
            elif hasattr(osint, 'search'):
                return await osint.search(name, search_type='person')
            else:
                return {"status": "error", "message": "No person search method found"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def _run_eye_d_email(self, osint, email: str) -> Dict:
        """Run EYE-D email search."""
        try:
            if hasattr(osint, 'search_email'):
                return await osint.search_email(email)
            elif hasattr(osint, 'search'):
                return await osint.search(email, search_type='email')
            else:
                return {"status": "error", "message": "No email search method found"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def _run_eye_d_phone(self, osint, phone: str) -> Dict:
        """Run EYE-D phone search."""
        try:
            if hasattr(osint, 'search_phone'):
                return await osint.search_phone(phone)
            elif hasattr(osint, 'search'):
                return await osint.search(phone, search_type='phone')
            else:
                return {"status": "error", "message": "No phone search method found"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _extract_facebook_ids_from_eye_d(self, eye_d_result: Dict) -> List[Dict]:
        """
        Extract Facebook numeric IDs from EYE-D/OSINT Industries results.

        OSINT Industries sometimes returns Facebook user IDs in id_int or id_str
        when the module is Facebook-related. These IDs can be used to construct
        profile URLs: https://www.facebook.com/profile.php?id={facebook_id}

        Returns list of dicts with:
          - facebook_id: The numeric user ID
          - profile_url: The constructed profile URL
          - module: Source module name
          - source_data: Original result data for reference
        """
        facebook_ids = []

        if not eye_d_result or not isinstance(eye_d_result, dict):
            return facebook_ids

        # Navigate to the results array
        results = eye_d_result.get('results', [])

        for result_item in results:
            if not isinstance(result_item, dict):
                continue

            source = result_item.get('source', '').lower()
            data = result_item.get('data', [])

            # Only process OSINT Industries results
            if 'osint' not in source and 'industries' not in source:
                continue

            # data is a list of OSINTResult objects (or dicts if serialized)
            if not isinstance(data, list):
                data = [data]

            for osint_result in data:
                # Check if it's a Facebook-related module
                module_name = ''
                fb_id = None

                if hasattr(osint_result, 'module'):
                    # It's an OSINTResult dataclass
                    module_name = osint_result.module.lower() if osint_result.module else ''
                    if 'facebook' in module_name or 'fb' in module_name:
                        fb_id = osint_result.id_int or osint_result.id_str
                elif isinstance(osint_result, dict):
                    # It's a serialized dict
                    module_name = str(osint_result.get('module', '')).lower()
                    if 'facebook' in module_name or 'fb' in module_name:
                        fb_id = osint_result.get('id_int') or osint_result.get('id_str')

                # If we found a Facebook ID, construct the profile URL
                if fb_id:
                    fb_id_str = str(fb_id).strip()
                    if fb_id_str.isdigit():  # Ensure it's numeric
                        profile_url = f"https://www.facebook.com/profile.php?id={fb_id_str}"
                        facebook_ids.append({
                            'facebook_id': fb_id_str,
                            'profile_url': profile_url,
                            'module': module_name,
                            'source_data': osint_result if isinstance(osint_result, dict) else None
                        })

        return facebook_ids

    async def _scrape_facebook_profile(self, facebook_id: str, profile_url: str = None) -> Dict:
        """
        Scrape a Facebook profile using BrightData Web Unlocker API.

        Args:
            facebook_id: The numeric Facebook user ID
            profile_url: Optional pre-constructed URL. If not provided, constructs from ID.

        Returns:
            Dict with scraped profile data or error information
        """
        import aiohttp

        if not profile_url:
            profile_url = f"https://www.facebook.com/profile.php?id={facebook_id}"

        api_key = os.getenv('BRIGHTDATA_API_KEY')
        if not api_key:
            return {
                "status": "skipped",
                "reason": "BRIGHTDATA_API_KEY not set",
                "facebook_id": facebook_id,
                "profile_url": profile_url
            }

        # BrightData Web Unlocker API endpoint
        # Using the scraping browser API for JavaScript-rendered content
        brightdata_url = "https://api.brightdata.com/request"

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "zone": "web_unlocker",
            "url": profile_url,
            "format": "raw",
            "render_js": True,
            "wait_for_selector": "[data-pagelet='ProfileTimeline']",  # Wait for profile content
            "timeout": 30000
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    brightdata_url,
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    if response.status == 200:
                        content = await response.text()
                        return {
                            "status": "success",
                            "facebook_id": facebook_id,
                            "profile_url": profile_url,
                            "html_content": content[:50000] if content else None,  # Truncate large HTML
                            "content_length": len(content) if content else 0
                        }
                    else:
                        error_text = await response.text()
                        return {
                            "status": "error",
                            "facebook_id": facebook_id,
                            "profile_url": profile_url,
                            "error": f"BrightData API error: {response.status}",
                            "details": error_text[:500]
                        }
        except asyncio.TimeoutError:
            return {
                "status": "error",
                "facebook_id": facebook_id,
                "profile_url": profile_url,
                "error": "Request timeout (60s)"
            }
        except Exception as e:
            return {
                "status": "error",
                "facebook_id": facebook_id,
                "profile_url": profile_url,
                "error": str(e)
            }

    async def _check_sanctions(self, name: str, entity_type: str) -> Dict:
        """Check OpenSanctions API."""
        api_key = os.getenv('OPENSANCTIONS_API_KEY')
        if not api_key:
            return {"status": "skipped", "reason": "OPENSANCTIONS_API_KEY not set"}

        try:
            import aiohttp
            schema = 'Person' if entity_type == 'person' else 'Company'
            url = "https://api.opensanctions.org/match/default"
            headers = {"Authorization": f"ApiKey {api_key}"}
            payload = {
                "queries": {
                    "q1": {
                        "schema": schema,
                        "properties": {"name": [name]}
                    }
                }
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return {"status": "ok", "matches": data.get("responses", {}).get("q1", {}).get("results", [])}
                    else:
                        return {"status": "error", "code": resp.status}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def _search_opencorporates(self, company_name: str, jurisdiction: str = None) -> Dict:
        """Search OpenCorporates API."""
        api_key = os.getenv('OPENCORPORATES_API_KEY')

        try:
            import aiohttp
            url = f"https://api.opencorporates.com/v0.4/companies/search?q={company_name}"
            if jurisdiction:
                url += f"&jurisdiction_code={jurisdiction.lower()}"
            if api_key:
                url += f"&api_token={api_key}"

            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        companies = data.get("results", {}).get("companies", [])
                        return {"status": "ok", "count": len(companies), "companies": companies[:10]}
                    else:
                        return {"status": "error", "code": resp.status}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def _whois_lookup(self, domain: str) -> Dict:
        """WHOIS lookup for domain using ALLDOM native bridge (WhoisXML API).

        Returns HISTORIC WHOIS by default - all ownership records over time.
        This reveals shell company networks and ownership changes.
        """
        # Use ALLDOM WHOIS bridge if available (WhoisXML API) - HISTORIC by default
        if ALLDOM_WHOIS_AVAILABLE and alldom_whois_history:
            try:
                result = await alldom_whois_history(domain)
                if result.get("status") == "ok":
                    records = result.get("records", [])
                    # Get current (most recent) record for top-level fields
                    current = records[0] if records else {}
                    return {
                        "status": "ok",
                        "source": "alldom_whoisxml_history",
                        "mode": "historic",
                        "records_count": len(records),
                        # Current registrant info
                        "registrar": current.get("registrar"),
                        "creation_date": current.get("created_date"),
                        "expiration_date": current.get("expires_date"),
                        "updated_date": current.get("updated_date"),
                        "name_servers": current.get("nameservers", []),
                        "registrant": current.get("registrant_name"),
                        "registrant_org": current.get("registrant_org"),
                        "registrant_email": current.get("registrant_email"),
                        "registrant_country": current.get("registrant_country"),
                        "status_codes": current.get("status", []),
                        # All historic records (reveals ownership changes)
                        "historic_records": records,
                        # All distinct registrants over time
                        "distinct_registrants": result.get("distinct_registrants", []),
                        # Extracted entities from all records
                        "extracted_entities": result.get("entities", []),
                    }
                else:
                    return result
            except Exception as e:
                logger.warning(f"ALLDOM WHOIS history failed, trying current lookup: {e}")
                # Fallback to current-only if history fails
                if alldom_whois_lookup:
                    try:
                        result = await alldom_whois_lookup(domain)
                        if result.get("status") == "ok":
                            return {
                                "status": "ok",
                                "source": "alldom_whoisxml",
                                "mode": "current",
                                "registrar": result.get("registrar"),
                                "creation_date": result.get("created_date"),
                                "expiration_date": result.get("expires_date"),
                                "name_servers": result.get("nameservers", []),
                                "registrant": result.get("registrant_name"),
                                "registrant_org": result.get("registrant_org"),
                                "registrant_email": result.get("registrant_email"),
                                "registrant_country": result.get("registrant_country"),
                            }
                    except Exception as e2:
                        logger.warning(f"ALLDOM WHOIS current also failed: {e2}")

        # Fallback to basic python-whois if ALLDOM not available
        try:
            import whois
            w = whois.whois(domain)
            return {
                "status": "ok",
                "source": "python_whois",
                "registrar": w.registrar,
                "creation_date": str(w.creation_date) if w.creation_date else None,
                "expiration_date": str(w.expiration_date) if w.expiration_date else None,
                "name_servers": w.name_servers if w.name_servers else [],
                "registrant": w.name if hasattr(w, 'name') else None
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def _search_aleph(self, query: str, jurisdiction: str = None, entity_type: str = 'company') -> Dict:
        """
        Search OCCRP Aleph - 237 collections across 75+ jurisdictions.

        Args:
            query: Search query (company name, person name, etc.)
            jurisdiction: ISO country code (e.g., 'GB', 'US', 'RU') - for context only
            entity_type: 'company', 'person', or 'document'

        Returns:
            Dict with status, results_count, results
        """
        if not self._aleph:
            return {"status": "skipped", "reason": "OCCRP Aleph module not available"}

        try:
            # Map entity type to Aleph schema
            schema_map = {
                'company': ['Company', 'LegalEntity'],
                'person': ['Person'],
                'document': ['Document']
            }
            schemas = schema_map.get(entity_type, ['Company', 'LegalEntity'])

            # Initialize searcher
            searcher = self._aleph()

            # Search Aleph (searches all collections)
            results = await searcher.search(
                query=query,
                max_results=50,
                schemas=schemas
            )

            # Add jurisdiction context if available
            if jurisdiction and self._aleph_collections:
                jurisdiction_data = self._aleph_collections.get('by_jurisdiction', {}).get(jurisdiction.upper(), {})
                jurisdiction_name = jurisdiction_data.get('name', jurisdiction) if jurisdiction_data else jurisdiction
            else:
                jurisdiction_name = jurisdiction

            return {
                "status": "ok",
                "results_count": len(results),
                "results": results,
                "query": query,
                "jurisdiction": jurisdiction_name,
                "entity_type": entity_type,
                "schemas_searched": schemas
            }

        except Exception as e:
            logger.error(f"Aleph search error: {e}")
            return {"status": "error", "message": str(e)}

    # =========================================================================
    # BRIGHTDATA - Web Scraping Only (for protected registry sites)
    # NOTE: For SERP search, use brute.py or Firecrawl search endpoint
    # =========================================================================

    async def _brightdata_scrape(self, url: str) -> Dict:
        """
        Scrape a webpage via BrightData Web Unlocker.

        Returns markdown content of the page.
        Can bypass bot detection and CAPTCHAs.
        """
        if not self._brightdata_available:
            return {"status": "skipped", "reason": "BRIGHTDATA_API_KEY not set"}

        try:
            import aiohttp

            api_url = "https://api.brightdata.com/request"
            headers = {
                "Authorization": f"Bearer {self._brightdata_api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "zone": "web_unlocker1",
                "url": url,
                "format": "raw"
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(api_url, json=payload, headers=headers, timeout=60) as resp:
                    if resp.status == 200:
                        content = await resp.text()
                        return {
                            "status": "ok",
                            "url": url,
                            "content_length": len(content),
                            "content": content[:5000]  # First 5K chars
                        }
                    else:
                        error_text = await resp.text()
                        return {"status": "error", "code": resp.status, "message": error_text[:200]}

        except asyncio.TimeoutError:
            return {"status": "error", "message": "Request timeout"}
        except Exception as e:
            return {"status": "error", "message": str(e)}


class IORouter:
    """Standalone routing logic for the I/O Matrix

    Enhanced with methodology intelligence:
    - atoms: 30 canonical methodology types (registry, media, osint, etc.)
    - enriched_sources: 713 sources with capabilities and success rates
    - jurisdictions: 99 country profiles with strengths/gaps

    Can optionally use IOCompiler for canonical file access.
    """

    def __init__(self, compiler: "IOCompiler" = None):
        self.legend: Dict[str, str] = {}
        self.reverse_legend: Dict[str, int] = {}
        self.rules: List[Dict] = []
        self.playbooks: List[Dict] = []  # Generated playbooks for strategic routing
        self.all_routes: List[Dict] = []  # Combined rules + playbooks for BFS
        self.sources: Any = {}

        # Methodology intelligence (from synthesized patterns)
        self.atoms: Dict[str, Dict] = {}  # 30 canonical methodology types
        self.enriched_sources: Dict[str, Dict] = {}  # 713 sources with capabilities
        self.jurisdictions: Dict[str, Dict] = {}  # 99 country capability profiles

        # Use IOCompiler if provided, otherwise create one if available
        self._compiler = compiler
        if self._compiler is None and IO_COMPILER_AVAILABLE:
            try:
                self._compiler = IOCompiler()
                self._compiler.compile()
            except Exception:
                self._compiler = None

        self._load_data()

    def _load_data(self):
        """Load matrix data files.

        Uses IOCompiler for canonical files when available:
        - codes.json (legend) via IOCompiler._codes
        - rules.json via direct load (IOCompiler also loads this)
        - sources_core.json via IOCompiler._manifest
        - jurisdictions.json via IOCompiler._jurisdictions

        Falls back to legacy files (legend.json, sources_v4.json) if needed.
        """
        # =====================================================================
        # LEGEND / CODES - Prefer IOCompiler.codes.json, fallback to legend.json
        # =====================================================================
        if self._compiler and hasattr(self._compiler, '_codes') and self._compiler._codes:
            # Build legend from codes.json: {code_str: field_name}
            for code_str, code_data in self._compiler._codes.items():
                if isinstance(code_data, dict):
                    self.legend[code_str] = code_data.get("name", f"unknown_{code_str}")
                else:
                    self.legend[code_str] = str(code_data)
            self.reverse_legend = {v: int(k) for k, v in self.legend.items()}
        else:
            # Fallback to legacy legend.json
            legend_path = MATRIX_DIR / "legend.json"
            if legend_path.exists():
                with open(legend_path) as f:
                    self.legend = json.load(f)
                    self.reverse_legend = {v: int(k) for k, v in self.legend.items()}

        # =====================================================================
        # FLOWS (unified) - Contains all routing intelligence by jurisdiction
        # Replaces the old separate rules.json file
        # =====================================================================
        flows_path = MATRIX_DIR / "flows.json"
        if flows_path.exists():
            with open(flows_path) as f:
                flows_data = json.load(f)

            # New format: {"meta": {...}, "flows": {jurisdiction: [flows]}}
            if isinstance(flows_data, dict) and 'flows' in flows_data:
                self.flows_by_jurisdiction = flows_data.get('flows', {})
                # Flatten to list for BFS routing (backwards compatible)
                self.rules = []
                for jur, jur_flows in self.flows_by_jurisdiction.items():
                    if isinstance(jur_flows, list):
                        for flow in jur_flows:
                            # Ensure jurisdiction is set
                            if 'jurisdiction' not in flow:
                                flow['jurisdiction'] = jur
                            self.rules.append(flow)
            else:
                # Old format: {jurisdiction: [flows]} without meta wrapper
                self.flows_by_jurisdiction = flows_data
                self.rules = []
                for jur, jur_flows in flows_data.items():
                    if isinstance(jur_flows, list):
                        for flow in jur_flows:
                            if 'jurisdiction' not in flow:
                                flow['jurisdiction'] = jur
                            self.rules.append(flow)

        # =====================================================================
        # PLAYBOOKS - Generated from methodology patterns
        # =====================================================================
        playbooks_path = MATRIX_DIR / "playbooks_validated.json"
        if not playbooks_path.exists():
            playbooks_path = MATRIX_DIR / "playbooks.json"  # Fallback

        if playbooks_path.exists():
            with open(playbooks_path) as f:
                all_playbooks = json.load(f)
                # Only include playbooks with routing fields (requires_any, returns)
                self.playbooks = [
                    p for p in all_playbooks
                    if p.get('requires_any') and p.get('returns')
                ]

        # Combine rules + playbooks for unified BFS routing
        self.all_routes = self.rules + self.playbooks

        # =====================================================================
        # SOURCES - Prefer IOCompiler (sources_core.json), fallback to v4/v2
        # =====================================================================
        if self._compiler and hasattr(self._compiler, '_manifest') and self._compiler._manifest:
            # Convert UnifiedSource objects to dict format expected by legacy code
            self.sources = {}
            for domain, source in self._compiler._manifest.items():
                jur = source.jurisdictions[0] if source.jurisdictions else "GLOBAL"
                if jur not in self.sources:
                    self.sources[jur] = []
                self.sources[jur].append(source.to_dict() if hasattr(source, 'to_dict') else source)
        else:
            # Fallback to legacy sources
            sources_path = MATRIX_DIR / "sources_v4.json"
            if not sources_path.exists():
                sources_path = MATRIX_DIR / "sources_v2.json"
            if sources_path.exists():
                with open(sources_path) as f:
                    self.sources = json.load(f)

        # =====================================================================
        # METHODOLOGY INTELLIGENCE - Legacy files (still useful)
        # =====================================================================
        atoms_path = MATRIX_DIR / "methodology_atoms.json"
        if atoms_path.exists():
            with open(atoms_path) as f:
                self.atoms = json.load(f)

        enriched_sources_path = MATRIX_DIR / "sources_enriched.json"
        if enriched_sources_path.exists():
            with open(enriched_sources_path) as f:
                self.enriched_sources = json.load(f)

        # =====================================================================
        # JURISDICTIONS - Prefer IOCompiler, fallback to legacy
        # =====================================================================
        if self._compiler and hasattr(self._compiler, '_jurisdictions') and self._compiler._jurisdictions:
            self.jurisdictions = self._compiler._jurisdictions
        else:
            jurisdictions_path = MATRIX_DIR / "jurisdiction_capabilities.json"
            if jurisdictions_path.exists():
                with open(jurisdictions_path) as f:
                    self.jurisdictions = json.load(f)

        # Jurisdiction intel (wisdom, tips)
        intel_path = MATRIX_DIR / "jurisdiction_intel.json"
        self.jurisdiction_intel = {}
        if intel_path.exists():
            with open(intel_path) as f:
                self.jurisdiction_intel = json.load(f)

        # =====================================================================
        # CONSOLIDATE INTO INTELLIGENCE MATRIX
        # =====================================================================
        self.matrix = self._consolidate_intelligence()
        self._link_execution_scripts()

    def _link_execution_scripts(self):
        """Walk BACKEND/modules and link python scripts to Atlas sources."""
        scripts_map = {}
        
        # Search for country-specific engines
        engines_path = BACKEND_PATH / "country_engines"
        if engines_path.exists():
            for jur_dir in engines_path.iterdir():
                if jur_dir.is_dir():
                    jur_code = jur_dir.name.upper()
                    for script in jur_dir.glob("*.py"):
                        scripts_map[f"{jur_code}_{script.stem}"] = str(script.relative_to(PROJECT_ROOT))

        # Search for core modules
        for module in ["corporella", "EYE-D", "LINKLATER", "JESTER"]:
            mod_path = BACKEND_PATH / module
            if mod_path.exists():
                for script in mod_path.glob("*.py"):
                    scripts_map[f"{module}_{script.stem}"] = str(script.relative_to(PROJECT_ROOT))

        # Link to Atlas sources
        for src_id, src in self.matrix["sources"].items():
            jur = src["jurisdiction"]
            # Look for matches: {JUR}_{name}, {module}_{name}, etc.
            name_clean = src["name"].lower().replace(".","_").replace(" ","_")

            for key, path in scripts_map.items():
                if jur in key or any(atom in key for atom in src["atoms"]):
                    if name_clean in key or key.lower() in name_clean:
                        src["execution_script"] = path
                        break

    def resolve_code(self, input_str: str) -> Optional[int]:
        """Resolve a field name to its numeric code.

        Supports:
        - Direct numeric codes (e.g., "13" -> 13)
        - Exact field names (e.g., "company_name" -> 13)
        - Partial matches (e.g., "company" -> 13)
        - Entity type shorthand (e.g., "company" -> 13, "person" -> 7)
        """
        if not input_str:
            return None

        input_lower = input_str.lower().strip()

        # Direct numeric code
        if input_lower.isdigit():
            return int(input_lower)

        # Entity type shorthand
        entity_map = {
            'person': 7, 'company': 13, 'email': 1, 'phone': 2,
            'domain': 6, 'username': 3, 'linkedin': 5, 'linkedin_url': 5,
            'address': 20, 'url': 22
        }
        if input_lower in entity_map:
            return entity_map[input_lower]

        # Exact match in reverse_legend
        if input_lower in self.reverse_legend:
            return self.reverse_legend[input_lower]

        # Partial match - check if field name starts with input
        for name, code in self.reverse_legend.items():
            if name.lower().startswith(input_lower):
                return code

        return None

    def _consolidate_intelligence(self) -> Dict[str, Any]:
        """Merge all sources, stats, and wisdom into a single source of truth."""
        atlas = {
            "sources": {},
            "jurisdictions": {},
            "capabilities": defaultdict(list)
        }

        # 1. Map Jurisdictions (Stats + Wisdom)
        all_jur_codes = set(self.jurisdictions.keys())
        if "by_region" in self.jurisdiction_intel:
            for region in self.jurisdiction_intel["by_region"].values():
                all_jur_codes.update(region)

        for code in all_jur_codes:
            stats = self.jurisdictions.get(code, {})
            wisdom = {}
            # Reach into intel to find wisdom for this code
            if "by_region" in self.jurisdiction_intel:
                # jurisdiction_intel is grouped by region, need to find the code
                pass # Placeholder for actual lookup if needed

            atlas["jurisdictions"][code] = {
                "code": code,
                "stats": stats,
                "wisdom": wisdom,
                "sources": []
            }

        # 2. Consolidate Sources (v4 + Enriched + Atoms)
        # self.sources is { "JUR": [source1, source2] }
        if isinstance(self.sources, dict):
            for jur, source_list in self.sources.items():
                for src in source_list:
                    src_id = src.get("id") or src.get("domain")
                    if not src_id: continue

                    # Enrich with wisdom from enriched_sources.json
                    # Note: enriched_sources keys are often domains
                    domain = src.get("domain", "")
                    enriched = self.enriched_sources.get(domain, {})
                    
                    # Build the complete resource object
                    resource = {
                        "id": src_id,
                        "name": src.get("name") or enriched.get("name") or domain,
                        "url": src.get("url") or enriched.get("url"),
                        "jurisdiction": jur,
                        "atoms": src.get("methodology", {}).get("atoms", []) or enriched.get("atoms", []),
                        "friction": src.get("methodology", {}).get("friction") or enriched.get("friction"),
                        "success_rate": src.get("methodology", {}).get("success_rate") or enriched.get("success_rate"),
                        "search_template": src.get("search_template") or src.get("url"),
                        "intel": src.get("metadata", {}).get("search_notes") or enriched.get("description"),
                        "outputs": src.get("outputs", []) or enriched.get("returns", [])
                    }

                    atlas["sources"][src_id] = resource
                    if jur in atlas["jurisdictions"]:
                        atlas["jurisdictions"][jur]["sources"].append(src_id)
                    
                    # Map to capabilities (inputs -> outputs)
                    for out_code in resource["outputs"]:
                        atlas["capabilities"][out_code].append(src_id)

        return atlas

    def get_full_intel(self, jurisdiction: str = None, input_type: str = None, output_type: str = None) -> Dict[str, Any]:
        """The 'Whatever the fuck we need' query function.
        Aggregates stats, URLs, scripts, and wisdom for a given context.
        """
        result = {
            "jurisdiction": {},
            "applicable_sources": [],
            "rules": [],
            "playbooks": []
        }

        # 1. Get Jurisdiction Intel
        if jurisdiction:
            result["jurisdiction"] = self.matrix["jurisdictions"].get(jurisdiction.upper(), {})

        # 2. Find Sources for Input/Output
        target_sources = set()
        in_code = self.resolve_code(input_type) if input_type else None
        out_code = self.resolve_code(output_type) if output_type else None

        for src_id, src in self.matrix["sources"].items():
            match = True
            if jurisdiction and src["jurisdiction"] != jurisdiction.upper():
                match = False
            if in_code and in_code not in src.get("inputs", []):
                # Note: v4 sources often have empty inputs list, fallback to type match
                pass
            if out_code and out_code not in src["outputs"]:
                match = False
            
            if match:
                target_sources.add(src_id)

        result["applicable_sources"] = [self.matrix["sources"][sid] for sid in target_sources]

        # 3. Find Rules and Playbooks
        for rule in self.rules:
            if in_code and in_code in rule.get("requires_any", rule.get("inputs", [])):
                if not jurisdiction or rule.get("jurisdiction") in (jurisdiction.upper(), "GLOBAL", None):
                    result["rules"].append(rule)

        for pb in self.playbooks:
            if in_code and in_code in pb.get("requires_any", []):
                if not jurisdiction or pb.get("jurisdiction") == jurisdiction.upper():
                    result["playbooks"].append(pb)

        return result

    def get_field_name(self, code: int) -> str:
        """Get human-readable field name"""
        return self.legend.get(str(code), f"unknown_{code}")

    def find_capabilities(self, have_field: str) -> Dict[str, Any]:
        """Find what outputs are possible given an input field"""
        code = self.resolve_code(have_field)
        if code is None:
            return {"error": f"Unknown field: {have_field}"}

        direct_outputs = set()
        via_rules = []
        via_playbooks = []

        # Check both rules and playbooks (all_routes)
        for route in self.all_routes:
            # Handle both old (inputs/outputs) and new (requires_any/returns) formats
            requires_any = route.get("requires_any", route.get("inputs", []))
            requires_all = route.get("requires_all", [])
            returns = route.get("returns", route.get("outputs", []))
            is_playbook = route.get("category") == "playbook"

            # Check if this route can be triggered by our input
            if code in requires_any or (not requires_any and not requires_all):
                for out_code in returns:
                    direct_outputs.add(out_code)

                route_info = {
                    "rule_id": route.get("id", "unknown"),
                    "label": route.get("label", route.get("source", "unknown")),
                    "outputs": [self.get_field_name(o) for o in returns]
                }

                if is_playbook:
                    route_info["type"] = "playbook"
                    route_info["success_rate"] = route.get("success_rate")
                    route_info["jurisdiction"] = route.get("jurisdiction")
                    via_playbooks.append(route_info)
                else:
                    via_rules.append(route_info)

        return {
            "input": self.get_field_name(code),
            "input_code": code,
            "direct_outputs": [
                {"code": c, "name": self.get_field_name(c)}
                for c in sorted(direct_outputs)
            ],
            "rules_count": len(via_rules),
            "playbooks_count": len(via_playbooks),
            "sample_rules": via_rules[:5],
            "sample_playbooks": via_playbooks[:5]
        }

    def find_route(self, have_field: str, want_field: str, max_depth: int = 3) -> Dict[str, Any]:
        """Find path from input field to desired output (includes playbooks)"""
        have_code = self.resolve_code(have_field)
        want_code = self.resolve_code(want_field)

        if have_code is None:
            return {"error": f"Unknown input field: {have_field}"}
        if want_code is None:
            return {"error": f"Unknown output field: {want_field}"}

        # BFS to find shortest path (uses all_routes = rules + playbooks)
        queue = deque([(have_code, [])])
        visited = {have_code}

        while queue:
            current, path = queue.popleft()

            if len(path) >= max_depth:
                continue

            for route in self.all_routes:
                requires_any = route.get("requires_any", route.get("inputs", []))
                returns = route.get("returns", route.get("outputs", []))
                is_playbook = route.get("category") == "playbook"

                if current in requires_any:
                    for output in returns:
                        step = {
                            "from": self.get_field_name(current),
                            "to": self.get_field_name(output),
                            "via": route.get("label", route.get("source", "unknown")),
                            "rule_id": route.get("id", "unknown")
                        }
                        if is_playbook:
                            step["type"] = "playbook"
                            step["success_rate"] = route.get("success_rate")
                        new_path = path + [step]

                        if output == want_code:
                            return {
                                "found": True,
                                "from": self.get_field_name(have_code),
                                "to": self.get_field_name(want_code),
                                "path": new_path,
                                "steps": len(new_path)
                            }

                        if output not in visited:
                            visited.add(output)
                            queue.append((output, new_path))

        return {
            "found": False,
            "from": self.get_field_name(have_code),
            "to": self.get_field_name(want_code),
            "message": f"No path found within {max_depth} steps"
        }

    def get_graph_data(self, center_field: str, depth: int = 2, max_sources: int = 30) -> Dict[str, Any]:
        """Get graph data centered on a field - groups sources by label, limits to top N"""
        code = self.resolve_code(center_field)
        if code is None:
            return {"error": f"Unknown field: {center_field}"}

        nodes = {}
        edges = []
        edge_set = set()  # Avoid duplicate edges

        def add_node(c: int, node_type: str = "entity"):
            if c not in nodes:
                nodes[c] = {
                    "id": c,
                    "label": self.get_field_name(c),
                    "type": node_type
                }

        def add_edge(from_id, to_id, edge_type):
            key = (str(from_id), str(to_id))
            if key not in edge_set:
                edge_set.add(key)
                edges.append({"from": from_id, "to": to_id, "type": edge_type})

        def explore(current_code: int, current_depth: int, visited_codes: set):
            if current_depth > depth:
                return
            if current_code in visited_codes:
                return
            visited_codes.add(current_code)

            add_node(current_code, "entity")

            # Group rules by label to avoid thousands of duplicate source nodes
            label_to_outputs = {}
            for rule in self.rules:
                requires_any = rule.get("requires_any", rule.get("inputs", []))
                returns = rule.get("returns", rule.get("outputs", []))

                if current_code in requires_any:
                    source_name = rule.get("label", rule.get("source", "unknown"))
                    # Skip blocked/junk sources
                    if source_name.startswith("BLOCKED") or source_name.startswith("'''"):
                        continue
                    if len(source_name) < 3:
                        continue
                    if source_name not in label_to_outputs:
                        label_to_outputs[source_name] = set()
                    for out_code in returns:
                        label_to_outputs[source_name].add(out_code)

            # Sort by number of outputs (most connected first) and limit
            sorted_sources = sorted(label_to_outputs.items(), key=lambda x: -len(x[1]))
            top_sources = sorted_sources[:max_sources]

            # Create ONE node per unique source label
            for source_name, output_codes in top_sources:
                source_id = f"src_{hash(source_name) & 0xFFFFFFFF}"

                if source_id not in nodes:
                    nodes[source_id] = {
                        "id": source_id,
                        "label": source_name,
                        "type": "source"
                    }

                # Edge from input to source
                add_edge(current_code, source_id, "input")

                # Edges from source to outputs
                for out_code in output_codes:
                    add_node(out_code, "entity")
                    add_edge(source_id, out_code, "output")

                    if current_depth < depth:
                        explore(out_code, current_depth + 1, visited_codes)

        explore(code, 0, set())

        # Mark frontier nodes (entities at max depth that could be explored further)
        entity_nodes = [n for n in nodes.values() if n["type"] == "entity"]
        for node in entity_nodes:
            # Check if this node has unexplored sources
            node_code = node["id"]
            has_more = False
            for rule in self.rules:
                requires_any = rule.get("requires_any", rule.get("inputs", []))
                if node_code in requires_any:
                    source_name = rule.get("label", rule.get("source", "unknown"))
                    if not source_name.startswith("BLOCKED") and not source_name.startswith("'''"):
                        source_id = f"src_{hash(source_name) & 0xFFFFFFFF}"
                        if source_id not in nodes:
                            has_more = True
                            break
            node["frontier"] = has_more

        return {
            "center": self.get_field_name(code),
            "center_code": code,
            "nodes": list(nodes.values()),
            "edges": edges,
            "node_count": len(nodes),
            "edge_count": len(edges)
        }

    def get_stats(self) -> Dict[str, Any]:
        """Get matrix statistics"""
        source_count = 0
        if isinstance(self.sources, dict):
            for jurisdiction in self.sources.values():
                if isinstance(jurisdiction, list):
                    source_count += len(jurisdiction)
                elif isinstance(jurisdiction, dict):
                    source_count += 1
        elif isinstance(self.sources, list):
            source_count = len(self.sources)

        # Count playbooks by type
        playbook_by_type = {}
        for pb in self.playbooks:
            pb_id = pb.get("id", "")
            if pb_id.startswith("PLAYBOOK_JUR_"):
                pb_type = "jurisdiction"
            elif pb_id.startswith("PLAYBOOK_ATOM_"):
                pb_type = "atom"
            elif pb_id.startswith("PLAYBOOK_SRC_"):
                pb_type = "source"
            elif pb_id.startswith("PLAYBOOK_FRICTION_"):
                pb_type = "friction"
            elif pb_id.startswith("PLAYBOOK_FULL_") or pb_id.startswith("PLAYBOOK_QUICK_") or pb_id.startswith("PLAYBOOK_SPECIALTY_"):
                pb_type = "composite"
            else:
                pb_type = "other"
            playbook_by_type[pb_type] = playbook_by_type.get(pb_type, 0) + 1

        return {
            "field_count": len(self.legend),
            "rule_count": len(self.rules),
            "playbook_count": len(self.playbooks),
            "playbook_breakdown": playbook_by_type,
            "total_routes": len(self.all_routes),
            "source_count": source_count,
            "uses_compiler": self._compiler is not None
        }

    def get_graph_rules_for_code(self, code: int) -> Dict[str, Any]:
        """Get graph creation rules for an output code (Pivot Principle).

        Determines whether a field code creates:
        - NODE: A pivotable entity (person, company, email, domain)
        - EDGE: A relationship between nodes (officer_of, shareholder_of)
        - METADATA: Properties on nodes/edges (status, date, percentage)

        Uses IOCompiler if available, otherwise returns basic info.
        """
        if self._compiler:
            return self._compiler.get_graph_rules_for_code(code)

        # Fallback: return basic info from legend
        field_name = self.get_field_name(code)
        return {
            "code": code,
            "field_name": field_name,
            "creates_node": False,
            "creates_edge": False,
            "is_metadata": True,  # Default to metadata
            "source": "fallback"
        }

    def get_module_for_jurisdiction(self, jurisdiction: str, entity_type: str = "company") -> str:
        """Get the module that handles a jurisdiction.

        Uses IOCompiler routing logic if available.
        """
        jur = jurisdiction.upper()

        # UK/GB has direct API
        if jur in ("UK", "GB"):
            return "uk"

        # Torpedo jurisdictions (EU registries with scraping recipes)
        torpedo_jurs = {"AT", "DE", "CH", "FR", "NL", "BE", "HR", "HU", "PL", "CZ", "SK", "SI", "IT", "ES"}
        if jur in torpedo_jurs:
            return "torpedo"

        # Person searches go to eye-d
        if entity_type == "person":
            return "eye-d"

        # Default to corporella (OpenCorporates aggregator)
        return "corporella"

    def find_playbooks(self, entity_type: str = None, jurisdiction: str = None,
                       min_success_rate: float = 0.0) -> List[Dict[str, Any]]:
        """Find playbooks matching criteria.

        Args:
            entity_type: Filter by trigger_type (company, person, domain, email)
            jurisdiction: Filter by jurisdiction code (HU, US, GB, etc.)
            min_success_rate: Minimum success rate (0.0-1.0)

        Returns:
            List of matching playbooks sorted by success_rate descending
        """
        results = []
        for pb in self.playbooks:
            # Apply filters
            if entity_type and pb.get("trigger_type") != entity_type:
                continue
            if jurisdiction and pb.get("jurisdiction") != jurisdiction:
                continue
            if pb.get("success_rate", 0) < min_success_rate:
                continue

            results.append({
                "id": pb.get("id"),
                "label": pb.get("label"),
                "trigger_type": pb.get("trigger_type"),
                "jurisdiction": pb.get("jurisdiction"),
                "success_rate": pb.get("success_rate"),
                "friction": pb.get("friction"),
                "inputs": [self.get_field_name(c) for c in pb.get("requires_any", [])],
                "outputs": [self.get_field_name(c) for c in pb.get("returns", [])[:5]],  # First 5
                "output_count": len(pb.get("returns", []))
            })

        # Sort by success rate descending
        results.sort(key=lambda x: x.get("success_rate", 0), reverse=True)
        return results

    def get_playbook(self, playbook_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific playbook by ID."""
        for pb in self.playbooks:
            if pb.get("id") == playbook_id:
                return pb
        return None

    def recommend_playbooks(
        self,
        entity_type: str,
        jurisdiction: str = None,
        top_n: int = 5,
        min_success_rate: float = 0.0,
        prefer_friction: str = None
    ) -> List[Dict[str, Any]]:
        """Smart playbook recommendation engine.

        Scores and ranks playbooks for a given entity type and jurisdiction,
        considering multiple factors for optimal selection.

        Args:
            entity_type: "company", "person", "domain", "email", "phone"
            jurisdiction: Optional 2-letter country code (e.g., "HU", "US")
            top_n: Number of recommendations to return (default 5)
            min_success_rate: Filter out playbooks below this success rate
            prefer_friction: Prefer "Open", "Restricted", or None for all

        Returns:
            Ranked list of recommended playbooks with scoring details

        Example:
            >>> router = IORouter()
            >>> recs = router.recommend_playbooks("company", "HU", top_n=3)
            >>> for r in recs:
            ...     print(f"{r['id']}: score={r['score']:.2f}")
        """
        # Map entity_type to trigger_type and input code
        type_map = {
            "company": {"trigger": "company", "code": 13},
            "person": {"trigger": "person", "code": 7},
            "email": {"trigger": "email", "code": 1},
            "domain": {"trigger": "domain", "code": 6},
            "phone": {"trigger": "phone", "code": 2},
        }

        mapping = type_map.get(entity_type.lower())
        if not mapping:
            return []

        trigger_type = mapping["trigger"]
        input_code = mapping["code"]

        # Friction scoring (lower is better)
        friction_scores = {
            "Open": 1.0,
            "Low": 0.9,
            "Medium": 0.7,
            "Restricted": 0.5,
            "High": 0.3,
            "Paywalled": 0.2,
        }

        # Regional jurisdiction groups for partial matches
        REGIONAL_GROUPS = {
            "EU": ["AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR",
                   "DE", "GR", "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL",
                   "PL", "PT", "RO", "SK", "SI", "ES", "SE"],
            "LATAM": ["AR", "BO", "BR", "CL", "CO", "CR", "CU", "DO", "EC", "SV",
                      "GT", "HN", "MX", "NI", "PA", "PY", "PE", "UY", "VE"],
            "MENA": ["AE", "BH", "DZ", "EG", "IQ", "JO", "KW", "LB", "LY", "MA",
                     "OM", "QA", "SA", "SY", "TN", "YE"],
            "APAC": ["AU", "BD", "CN", "HK", "ID", "IN", "JP", "KR", "MY", "NZ",
                     "PH", "PK", "SG", "TH", "TW", "VN"],
        }

        def get_jurisdiction_score(pb_jur: str, target_jur: str) -> float:
            """Score jurisdiction match: exact=1.0, regional=0.5, none=0.0"""
            if not target_jur or not pb_jur:
                return 0.0
            if pb_jur.upper() == target_jur.upper():
                return 1.0
            # Check regional match
            for region, countries in REGIONAL_GROUPS.items():
                if target_jur.upper() in countries and pb_jur.upper() in countries:
                    return 0.5
                if pb_jur.upper() == region and target_jur.upper() in countries:
                    return 0.4
            return 0.0

        scored_playbooks = []

        for pb in self.playbooks:
            # Must match trigger type OR accept our input code
            pb_trigger = pb.get("trigger_type")
            pb_requires = pb.get("requires_any", [])

            if pb_trigger != trigger_type and input_code not in pb_requires:
                continue

            # Success rate filter
            success_rate = pb.get("success_rate", 0.5)
            if success_rate < min_success_rate:
                continue

            # Friction filter
            pb_friction = pb.get("friction", "Medium")
            if prefer_friction and pb_friction != prefer_friction:
                continue

            # Calculate scores
            # 0. Trigger type match bonus - CRITICAL for correct entity filtering
            # Exact match = 1.0, partial (via requires_any) = 0.3
            trigger_match_score = 1.0 if pb_trigger == trigger_type else 0.3

            # 1. Success rate score (0-1)
            success_score = success_rate

            # 2. Jurisdiction score (0-1)
            jur_score = get_jurisdiction_score(pb.get("jurisdiction"), jurisdiction)

            # 3. Output richness score (normalized 0-1)
            outputs = pb.get("returns", [])
            output_score = min(len(outputs) / 20.0, 1.0)  # Cap at 20 outputs

            # 4. Friction score (0-1)
            friction_score = friction_scores.get(pb_friction, 0.5)

            # 5. Rule count score (more rules = more thorough)
            rules = pb.get("rules", [])
            rule_score = min(len(rules) / 10.0, 1.0)  # Cap at 10 rules

            # Combined score with weights
            # Trigger match is the most important factor (35%)
            # then jurisdiction (25%), success (20%), friction (10%), output (5%), rules (5%)
            if jurisdiction:
                total_score = (
                    trigger_match_score * 0.35 +
                    jur_score * 0.25 +
                    success_score * 0.20 +
                    friction_score * 0.10 +
                    output_score * 0.05 +
                    rule_score * 0.05
                )
            else:
                total_score = (
                    trigger_match_score * 0.40 +
                    success_score * 0.30 +
                    friction_score * 0.15 +
                    output_score * 0.10 +
                    rule_score * 0.05
                )

            scored_playbooks.append({
                "id": pb.get("id"),
                "label": pb.get("label"),
                "trigger_type": pb_trigger,
                "jurisdiction": pb.get("jurisdiction"),
                "success_rate": success_rate,
                "friction": pb_friction,
                "rule_count": len(rules),
                "output_count": len(outputs),
                "outputs_preview": [self.get_field_name(c) for c in outputs[:5]],
                "rules": rules[:5] if len(rules) > 5 else rules,
                "score": round(total_score, 3),
                "score_breakdown": {
                    "trigger_match": round(trigger_match_score, 2),
                    "success": round(success_score, 2),
                    "jurisdiction": round(jur_score, 2),
                    "output_richness": round(output_score, 2),
                    "friction": round(friction_score, 2),
                    "thoroughness": round(rule_score, 2)
                },
                "category": pb.get("category", "playbook")
            })

        # Sort by score descending
        scored_playbooks.sort(key=lambda x: x["score"], reverse=True)

        return scored_playbooks[:top_n]

    def search_legend(self, query: str) -> List[Dict[str, Any]]:
        """Search legend for matching fields"""
        query_lower = query.lower()
        results = []

        for code, name in self.legend.items():
            if query_lower in name.lower():
                results.append({
                    "code": int(code),
                    "name": name
                })

        return sorted(results, key=lambda x: x["name"])


# =============================================================================
# IO PLANNER - Multi-step investigation planning using enriched matrix
# =============================================================================

class IOPlanner:
    """Strategic investigation planner using enriched IO Matrix.

    Takes a task and plans optimal multi-step execution paths using:
    - Playbooks as coverage maximizers (one step, many outputs)
    - Jurisdiction intelligence (what works where)
    - Success rates (prefer reliable paths)
    - Dependency ordering (topological sort)

    Usage:
        planner = IOPlanner()
        plan = planner.plan_investigation("company", "Acme Kft", "HU", depth="full")
        # Returns ordered steps with playbooks and rules
    """

    # Goal profiles: what fields to target for each entity_type + depth
    GOAL_PROFILES = {
        # Company investigations
        "company_quick": [47, 58, 71],  # address, officers, shareholders
        "company_full": [47, 49, 50, 56, 58, 59, 60, 61, 71, 99, 100, 188, 241],
        "company_ubo": [71, 73, 74, 75],  # shareholders, shareholder_company, shareholder_person, shareholder_type
        "company_litigation": [188, 189, 190],  # litigation fields

        # Person investigations
        "person_quick": [170, 188, 241],  # person_address, litigation, extracted_companies
        "person_full": [170, 171, 188, 189, 190, 240, 241, 242],
        "person_pep": [203, 204, 205],  # PEP fields

        # Domain investigations
        "domain_quick": [131, 132, 141],  # registrant_person, registrant_company, whois_raw
        "domain_full": [130, 131, 132, 133, 134, 135, 136, 141, 191, 193, 200],  # ip, registrant fields, whois, backlinks, dns, subdomains

        # Email investigations
        "email_quick": [240, 241],  # extracted entities
        "email_full": [7, 170, 240, 241, 242],  # person_name, address, extractions
    }

    # Input field codes for each entity type
    ENTITY_INPUT_CODES = {
        "company": 13,   # company_name
        "person": 7,     # person_name
        "email": 1,      # email
        "domain": 6,     # domain_url
        "phone": 2,      # phone
    }

    def __init__(self, router: IORouter = None):
        self.router = router or IORouter()

    def plan_investigation(
        self,
        entity_type: str,
        value: str,
        jurisdiction: str = None,
        depth: str = "full"
    ) -> Dict[str, Any]:
        """Plan a multi-step investigation.

        Args:
            entity_type: "company", "person", "email", "domain", "phone"
            value: The entity value to investigate
            jurisdiction: Optional 2-letter country code (e.g., "HU")
            depth: "quick", "full", "ubo", "litigation", "pep"

        Returns:
            Execution plan with ordered steps
        """
        # 1. Get input field code
        input_code = self.ENTITY_INPUT_CODES.get(entity_type)
        if not input_code:
            return {"error": f"Unknown entity type: {entity_type}"}

        # 2. Get goal fields based on entity_type + depth
        profile_key = f"{entity_type}_{depth}"
        goal_codes = self.GOAL_PROFILES.get(profile_key, self.GOAL_PROFILES.get(f"{entity_type}_full", []))

        if not goal_codes:
            return {"error": f"No goal profile for: {profile_key}"}

        # 3. Find best playbook(s) for coverage
        best_playbooks = self._find_best_playbooks(input_code, goal_codes, jurisdiction)

        # 4. Calculate coverage from playbooks
        covered_by_playbooks = set()
        selected_playbooks = []

        for pb in best_playbooks:
            new_coverage = set(pb["returns"]) & set(goal_codes)
            if new_coverage - covered_by_playbooks:  # Adds new coverage
                selected_playbooks.append(pb)
                covered_by_playbooks.update(new_coverage)

            if covered_by_playbooks >= set(goal_codes):
                break  # Full coverage achieved

        # 5. Find rules for remaining gaps
        remaining_goals = set(goal_codes) - covered_by_playbooks
        gap_rules = self._find_gap_rules(input_code, list(remaining_goals))

        # 6. Build execution plan
        steps = []
        step_num = 1

        # Add playbooks first (they're coverage maximizers)
        for pb in selected_playbooks:
            steps.append({
                "order": step_num,
                "type": "playbook",
                "id": pb["id"],
                "label": pb.get("label", pb["id"]),
                "covers": [self.router.get_field_name(c) for c in pb["returns"] if c in goal_codes],
                "covers_codes": [c for c in pb["returns"] if c in goal_codes],
                "success_rate": pb.get("success_rate", 0),
                "jurisdiction": pb.get("jurisdiction"),
                "rules_inside": pb.get("rules", []),
                "execution_mode": pb.get("execution_mode", "parallel")
            })
            step_num += 1

        # Add gap rules
        for rule in gap_rules:
            steps.append({
                "order": step_num,
                "type": "rule",
                "id": rule["id"],
                "label": rule.get("label", rule["id"]),
                "covers": [self.router.get_field_name(c) for c in rule.get("returns", []) if c in remaining_goals],
                "covers_codes": [c for c in rule.get("returns", []) if c in remaining_goals],
                "success_rate": rule.get("success_rate"),
            })
            step_num += 1

        # 7. Calculate overall stats
        total_covered = covered_by_playbooks.union(
            set(c for r in gap_rules for c in r.get("returns", []) if c in remaining_goals)
        )
        coverage_pct = len(total_covered) / len(goal_codes) * 100 if goal_codes else 0

        avg_success = sum((s.get("success_rate") or 0.5) for s in steps) / len(steps) if steps else 0

        # 8. Add jurisdiction intelligence
        jur_intel = None
        if jurisdiction and jurisdiction in self.router.jurisdictions:
            jur_data = self.router.jurisdictions[jurisdiction]
            jur_intel = {
                "strengths": jur_data.get("strengths", []),
                "gaps": jur_data.get("gaps", []),
                "success_rate": jur_data.get("success_rate"),
                "friction": jur_data.get("primary_friction")
            }

        return {
            "entity": {
                "type": entity_type,
                "value": value,
                "jurisdiction": jurisdiction,
                "input_code": input_code
            },
            "goals": {
                "profile": profile_key,
                "fields": [{"code": c, "name": self.router.get_field_name(c)} for c in goal_codes],
                "count": len(goal_codes)
            },
            "plan": {
                "steps": steps,
                "step_count": len(steps),
                "coverage_percent": round(coverage_pct, 1),
                "estimated_success": round(avg_success, 2),
                "playbook_steps": len(selected_playbooks),
                "rule_steps": len(gap_rules)
            },
            "jurisdiction_intel": jur_intel,
            "uncovered": [
                {"code": c, "name": self.router.get_field_name(c)}
                for c in set(goal_codes) - total_covered
            ]
        }

    def _find_best_playbooks(
        self,
        input_code: int,
        goal_codes: List[int],
        jurisdiction: str = None
    ) -> List[Dict]:
        """Find playbooks that maximize coverage of goals."""
        scored = []

        for pb in self.router.playbooks:
            requires = pb.get("requires_any", [])
            returns = pb.get("returns", [])

            # Must accept our input
            if input_code not in requires:
                continue

            # Score by coverage
            covered = set(returns) & set(goal_codes)
            coverage_score = len(covered) / len(goal_codes) if goal_codes else 0

            # Bonus for jurisdiction match
            jur_bonus = 0.2 if jurisdiction and pb.get("jurisdiction") == jurisdiction else 0

            # Success rate factor
            success = pb.get("success_rate", 0.5)

            # Combined score
            score = (coverage_score * 0.5) + (success * 0.3) + jur_bonus

            scored.append({
                **pb,
                "_score": score,
                "_coverage": len(covered)
            })

        # Sort by score descending
        scored.sort(key=lambda x: (x["_score"], x["_coverage"]), reverse=True)
        return scored[:10]  # Top 10

    def _find_gap_rules(self, input_code: int, gap_codes: List[int]) -> List[Dict]:
        """Find individual rules to cover remaining gaps."""
        rules = []
        covered = set()

        for gap in gap_codes:
            if gap in covered:
                continue

            # Find a rule that produces this output
            for rule in self.router.rules:
                requires = rule.get("requires_any", rule.get("inputs", []))
                returns = rule.get("returns", rule.get("outputs", []))

                if input_code in requires and gap in returns:
                    rules.append(rule)
                    covered.update(returns)
                    break

        return rules

    def explain_plan(self, plan: Dict[str, Any]) -> str:
        """Generate human-readable explanation of a plan."""
        if "error" in plan:
            return f"Error: {plan['error']}"

        lines = []
        entity = plan["entity"]
        goals = plan["goals"]
        p = plan["plan"]

        lines.append(f"INVESTIGATION PLAN: {entity['type'].upper()} - {entity['value']}")
        if entity.get("jurisdiction"):
            lines.append(f"Jurisdiction: {entity['jurisdiction']}")
        lines.append("")

        lines.append(f"GOALS ({goals['count']} fields):")
        for g in goals["fields"][:5]:
            lines.append(f"  - {g['name']} ({g['code']})")
        if len(goals["fields"]) > 5:
            lines.append(f"  ... and {len(goals['fields']) - 5} more")
        lines.append("")

        lines.append(f"EXECUTION PLAN ({p['step_count']} steps, {p['coverage_percent']}% coverage):")
        for step in p["steps"]:
            step_type = "📦 PLAYBOOK" if step["type"] == "playbook" else "⚙️ RULE"
            lines.append(f"  Step {step['order']}: {step_type} {step['id']}")
            lines.append(f"           Covers: {', '.join(step['covers'][:3])}{'...' if len(step['covers']) > 3 else ''}")
            if step.get("success_rate"):
                lines.append(f"           Success: {step['success_rate']*100:.0f}%")
        lines.append("")

        if plan.get("jurisdiction_intel"):
            ji = plan["jurisdiction_intel"]
            lines.append(f"JURISDICTION INTEL ({entity['jurisdiction']}):")
            lines.append(f"  Strengths: {', '.join(ji['strengths'][:3])}")
            lines.append(f"  Gaps: {', '.join(ji['gaps'][:3])}")

        if plan.get("uncovered"):
            lines.append("")
            lines.append(f"⚠️ UNCOVERED ({len(plan['uncovered'])} fields):")
            for u in plan["uncovered"][:3]:
                lines.append(f"  - {u['name']}")

        return "\n".join(lines)

    def plan_chain(
        self,
        start_type: str,
        start_value: str,
        target_type: str,
        jurisdiction: str = None,
        max_depth: int = 5
    ) -> Dict[str, Any]:
        """Plan a multi-step chain from start entity to target entity type.

        This handles SEQUENTIAL dependencies where each step's output
        feeds into the next step's input.

        Args:
            start_type: Starting entity type ("company", "person", "domain", "email")
            start_value: The starting entity value
            target_type: What we ultimately want ("person", "ubo", "pep", "sanctions")
            jurisdiction: Optional country code
            max_depth: Maximum chain depth (prevent infinite loops)

        Returns:
            Multi-step execution chain with dependencies
        """
        # Field mappings
        type_to_code = {
            "company": 13, "person": 7, "email": 1, "domain": 6, "phone": 2
        }

        # Target profiles - what chain of fields to traverse
        TARGET_CHAINS = {
            # UBO: company → shareholders → (if company, recurse) → persons
            "ubo": {
                "description": "Ultimate Beneficial Owners",
                "chain": [
                    {"from": 13, "to": 71, "label": "Get shareholders"},  # company_name → shareholders
                    {"from": 71, "to": 73, "label": "Identify corporate shareholders", "branch": "company"},  # shareholders → shareholder_company
                    {"from": 71, "to": 74, "label": "Identify person shareholders", "branch": "person"},  # shareholders → shareholder_person
                    {"from": 73, "to": 71, "label": "Recurse: get shareholders of corporate shareholder", "recurse": True},
                ],
                "terminal": 74,  # End when we have person shareholders
            },
            # PEP check: person → pep status
            "pep": {
                "description": "Politically Exposed Person check",
                "chain": [
                    {"from": 7, "to": 99, "label": "Check sanctions"},
                    {"from": 7, "to": 100, "label": "Get sanctions details"},
                ],
                "terminal": 100,
            },
            # Company officers: company → officers → person details
            "officers": {
                "description": "Company officers with details",
                "chain": [
                    {"from": 13, "to": 58, "label": "Get officers list"},
                    {"from": 58, "to": 59, "label": "Get officer names"},
                    {"from": 59, "to": 7, "label": "Extract person entity", "yields": "person"},
                    {"from": 7, "to": 99, "label": "Check sanctions for each officer"},
                ],
                "terminal": 99,
            },
            # Full company: company → everything
            "full_company": {
                "description": "Complete company investigation",
                "chain": [
                    {"from": 13, "to": 47, "label": "Get address"},
                    {"from": 13, "to": 58, "label": "Get officers"},
                    {"from": 13, "to": 71, "label": "Get shareholders"},
                    {"from": 13, "to": 99, "label": "Check sanctions"},
                    {"from": 71, "to": 74, "label": "Get person shareholders", "yields": "person"},
                    {"from": 58, "to": 59, "label": "Get officer names", "yields": "person"},
                    {"from": 7, "to": 99, "label": "Check sanctions for persons"},
                ],
                "terminal": 99,
            },

            # =================================================================
            # DUE DILIGENCE - Full report based on actual report patterns
            # Based on 6,126 methodology patterns from 1,243 real reports
            # =================================================================
            "due_diligence": {
                "description": "Full Due Diligence Report (Corporate)",
                "sections": [
                    "Corporate Overview",
                    "Ownership Structure",
                    "Management & Key Personnel",
                    "Litigation & Court Records",
                    "Regulatory & Compliance",
                    "Financial Overview",
                    "Media & Reputation",
                    "Sanctions & PEP Screening",
                ],
                "chain": [
                    # PHASE 1: Corporate Registry (100% success in RO)
                    {"from": 13, "to": 47, "label": "1.1 Get registered address", "section": "Corporate Overview", "method": "corporate_registry_search"},
                    {"from": 13, "to": 49, "label": "1.2 Get company status", "section": "Corporate Overview", "method": "corporate_registry_search"},
                    {"from": 13, "to": 50, "label": "1.3 Get incorporation date", "section": "Corporate Overview", "method": "corporate_registry_search"},
                    {"from": 13, "to": 56, "label": "1.4 Get share capital", "section": "Corporate Overview", "method": "corporate_registry_search"},

                    # PHASE 2: Ownership Structure
                    {"from": 13, "to": 71, "label": "2.1 Get shareholders list", "section": "Ownership Structure", "method": "corporate_registry_search"},
                    {"from": 71, "to": 73, "label": "2.2 Identify corporate shareholders", "section": "Ownership Structure", "branch": "company"},
                    {"from": 71, "to": 74, "label": "2.3 Identify person shareholders", "section": "Ownership Structure", "branch": "person", "yields": "person"},
                    {"from": 73, "to": 71, "label": "2.4 Recurse: get parent company shareholders", "section": "Ownership Structure", "recurse": True},
                    {"from": 71, "to": 75, "label": "2.5 Get shareholding percentages", "section": "Ownership Structure"},

                    # PHASE 3: Management & Key Personnel
                    {"from": 13, "to": 58, "label": "3.1 Get officers list", "section": "Management & Key Personnel", "method": "corporate_registry_search"},
                    {"from": 58, "to": 59, "label": "3.2 Get officer names", "section": "Management & Key Personnel", "yields": "person"},
                    {"from": 58, "to": 60, "label": "3.3 Get officer roles", "section": "Management & Key Personnel"},
                    {"from": 58, "to": 61, "label": "3.4 Get appointment dates", "section": "Management & Key Personnel"},
                    {"from": 7, "to": 170, "label": "3.5 Get officer addresses", "section": "Management & Key Personnel", "method": "osint"},

                    # PHASE 4: Litigation & Court Records (93% success in RO)
                    {"from": 13, "to": 188, "label": "4.1 Search litigation records (company)", "section": "Litigation & Court Records", "method": "court_search"},
                    {"from": 7, "to": 188, "label": "4.2 Search litigation records (officers)", "section": "Litigation & Court Records", "method": "court_search"},
                    {"from": 188, "to": 189, "label": "4.3 Get case details", "section": "Litigation & Court Records"},
                    {"from": 13, "to": 113, "label": "4.4 Search insolvency records", "section": "Litigation & Court Records", "method": "insolvency_database_search"},

                    # PHASE 5: Regulatory & Compliance
                    {"from": 13, "to": 99, "label": "5.1 Sanctions screening (company)", "section": "Regulatory & Compliance", "method": "sanctions_screening"},
                    {"from": 7, "to": 99, "label": "5.2 Sanctions screening (persons)", "section": "Regulatory & Compliance", "method": "sanctions_screening"},
                    {"from": 7, "to": 100, "label": "5.3 Get sanctions details", "section": "Regulatory & Compliance"},
                    {"from": 13, "to": 114, "label": "5.4 Check regulatory filings", "section": "Regulatory & Compliance", "method": "regulatory_database_search"},
                    {"from": 13, "to": 115, "label": "5.5 Search public procurement", "section": "Regulatory & Compliance", "method": "public_procurement_search"},

                    # PHASE 6: Financial Overview (field 54=company_filings, 55=financial_year, 56=share_capital, 57=currency)
                    {"from": 13, "to": 54, "label": "6.1 Get company filings", "section": "Financial Overview", "method": "financial_database_search"},
                    {"from": 13, "to": 55, "label": "6.2 Get financial year data", "section": "Financial Overview"},
                    {"from": 13, "to": 56, "label": "6.3 Get share capital", "section": "Financial Overview"},

                    # PHASE 7: Media & Reputation (85% success in RO)
                    {"from": 13, "to": 241, "label": "7.1 Media monitoring (company)", "section": "Media & Reputation", "method": "media_monitoring"},
                    {"from": 7, "to": 241, "label": "7.2 Media monitoring (persons)", "section": "Media & Reputation", "method": "media_monitoring"},
                    {"from": 13, "to": 242, "label": "7.3 Extract mentioned entities", "section": "Media & Reputation", "yields": "company"},

                    # PHASE 8: OSINT & Digital Footprint
                    {"from": 13, "to": 6, "label": "8.1 Identify company domains", "section": "OSINT & Digital", "method": "osint"},
                    {"from": 6, "to": 141, "label": "8.2 WHOIS lookup", "section": "OSINT & Digital"},
                    {"from": 7, "to": 1, "label": "8.3 Find associated emails", "section": "OSINT & Digital", "method": "osint"},
                    {"from": 7, "to": 188, "label": "8.4 Social media research", "section": "OSINT & Digital", "method": "social_media_research"},
                ],
                "terminal": 241,  # Media mentions as final output
            },
        }

        start_code = type_to_code.get(start_type)
        if not start_code:
            return {"error": f"Unknown start type: {start_type}"}

        target_chain = TARGET_CHAINS.get(target_type)
        if not target_chain:
            return {"error": f"Unknown target type: {target_type}. Valid: {list(TARGET_CHAINS.keys())}"}

        # Build the execution steps
        steps = []
        step_num = 1

        for chain_step in target_chain["chain"]:
            from_code = chain_step["from"]
            to_code = chain_step["to"]

            # Find the best route for this step
            route = self.router.find_route(from_code, to_code)
            route_found = route.get("found", False)

            # Get the actual rule/playbook info if route exists
            path_info = route["path"][0] if route.get("path") else {}

            step = {
                "order": step_num,
                "from_field": self.router.get_field_name(from_code),
                "from_code": from_code,
                "to_field": self.router.get_field_name(to_code),
                "to_code": to_code,
                "label": chain_step["label"],
                "section": chain_step.get("section"),  # Report section (e.g., "Corporate Overview")
                "method": chain_step.get("method"),    # Research method (e.g., "corporate_registry_search")
            }

            if route_found:
                step["route"] = path_info.get("via", "direct")
                step["rule_id"] = path_info.get("rule_id")
                step["has_route"] = True
            else:
                # No direct route - this is a conceptual step (entity extraction, branching, etc.)
                step["route"] = "entity_extraction"
                step["rule_id"] = None
                step["has_route"] = False
                step["note"] = "No direct route - requires entity extraction from previous step"

            # Add branching/recursion info
            if chain_step.get("branch"):
                step["branch_type"] = chain_step["branch"]
                step["note"] = f"Branch: for each {chain_step['branch']}, continue chain"
            if chain_step.get("recurse"):
                step["recurse"] = True
                step["note"] = "Recurse: repeat from step 1 with this entity"
            if chain_step.get("yields"):
                step["yields"] = chain_step["yields"]
                if not step.get("note"):
                    step["note"] = f"Yields new {chain_step['yields']} entities for further processing"

            steps.append(step)
            step_num += 1

        # Add jurisdiction intelligence
        jur_intel = None
        if jurisdiction and jurisdiction in self.router.jurisdictions:
            jur_data = self.router.jurisdictions[jurisdiction]
            jur_intel = {
                "strengths": jur_data.get("strengths", []),
                "gaps": jur_data.get("gaps", []),
            }

        return {
            "chain_type": target_type,
            "description": target_chain["description"],
            "start": {
                "type": start_type,
                "value": start_value,
                "code": start_code,
                "jurisdiction": jurisdiction
            },
            "terminal_field": {
                "code": target_chain["terminal"],
                "name": self.router.get_field_name(target_chain["terminal"])
            },
            "steps": steps,
            "step_count": len(steps),
            "has_recursion": any(s.get("recurse") for s in steps),
            "has_branching": any(s.get("branch_type") for s in steps),
            "jurisdiction_intel": jur_intel
        }

    def explain_chain(self, chain: Dict[str, Any]) -> str:
        """Generate human-readable explanation of a chain."""
        if "error" in chain:
            return f"Error: {chain['error']}"

        lines = []
        lines.append(f"CHAIN: {chain['description'].upper()}")
        lines.append(f"Start: {chain['start']['type']} = \"{chain['start']['value']}\"")
        if chain['start'].get('jurisdiction'):
            lines.append(f"Jurisdiction: {chain['start']['jurisdiction']}")
        lines.append(f"Target: {chain['terminal_field']['name']}")
        lines.append("")

        if chain.get("has_recursion"):
            lines.append("⚠️  This chain has RECURSION (follows ownership chains)")
        if chain.get("has_branching"):
            lines.append("⚠️  This chain has BRANCHING (splits by entity type)")
        lines.append("")

        # Check if steps have sections (for due_diligence chains)
        has_sections = any(s.get("section") for s in chain.get("steps", []))

        if has_sections:
            # Group by section
            current_section = None
            lines.append(f"EXECUTION PLAN ({chain['step_count']} steps):")
            lines.append("=" * 60)

            for step in chain["steps"]:
                section = step.get("section", "Other")
                if section != current_section:
                    lines.append("")
                    lines.append(f"▶ {section.upper()}")
                    lines.append("-" * 40)
                    current_section = section

                method = step.get("method", "")
                method_str = f" [{method}]" if method else ""
                lines.append(f"  {step['label']}{method_str}")
                lines.append(f"    {step['from_field']} → {step['to_field']}")
                lines.append(f"    Route: {step['route']}")
                if step.get("note"):
                    lines.append(f"    📌 {step['note']}")
        else:
            # Original flat format
            lines.append(f"STEPS ({chain['step_count']}):")
            lines.append("-" * 50)

            for step in chain["steps"]:
                lines.append(f"Step {step['order']}: {step['label']}")
                lines.append(f"         {step['from_field']} ({step['from_code']}) → {step['to_field']} ({step['to_code']})")
                lines.append(f"         Via: {step['route']}")
                if step.get("note"):
                    lines.append(f"         📌 {step['note']}")
                lines.append("")

        lines.append("")
        if chain.get("jurisdiction_intel"):
            ji = chain["jurisdiction_intel"]
            lines.append("JURISDICTION INTEL:")
            lines.append(f"  Strengths: {', '.join(ji['strengths'][:3])}")
            if ji.get('gaps'):
                lines.append(f"  Gaps: {', '.join(ji['gaps'][:3])}")

        return "\n".join(lines)

    def select_sources(
        self,
        step: Dict[str, Any],
        jurisdiction: str = None,
        max_sources: int = 3
    ) -> List[Dict[str, Any]]:
        """Select actual source URLs for a chain step.

        Matches sources based on:
        1. Method pattern (e.g., 'corporate_registry_search')
        2. Jurisdiction (if provided)
        3. Success rate (descending)
        4. Friction level (prefer 'open')

        Args:
            step: A chain step dict with 'method', 'from_code', 'to_code'
            jurisdiction: 2-letter country code
            max_sources: Maximum sources to return

        Returns:
            List of source dicts with url, name, success_rate
        """
        method = step.get("method", "")
        candidates = []

        # router.sources is organized by jurisdiction: {jur_code: [source1, source2, ...]}
        jurisdictions_to_search = []
        if jurisdiction:
            jurisdictions_to_search = [jurisdiction, "GLOBAL", "Global", "INTL"]
        else:
            jurisdictions_to_search = list(self.router.sources.keys())

        for jur in jurisdictions_to_search:
            sources_list = self.router.sources.get(jur, [])
            if not isinstance(sources_list, list):
                continue

            for source in sources_list:
                if not isinstance(source, dict):
                    continue

                # Check method match via methodology.atoms or thematic_tags
                methodology = source.get("methodology", {})
                atoms = methodology.get("atoms", [])
                thematic = source.get("thematic_tags", [])

                method_match = False
                if method:
                    # Map method names to atoms
                    method_to_atom = {
                        "corporate_registry_search": ["REGISTRY_COMPANY"],
                        "court_search": ["REGISTRY_COURT"],
                        "sanctions_screening": ["COMPLIANCE_SANCTIONS"],
                        "media_monitoring": ["MEDIA_MONITORING"],
                        "osint": ["OSINT_GENERAL", "OSINT_DOMAIN"],
                        "insolvency_database_search": ["REGISTRY_INSOLVENCY"],
                        "regulatory_database_search": ["COMPLIANCE_REGULATORY"],
                        "public_procurement_search": ["REGISTRY_PROCUREMENT"],
                        "financial_database_search": ["FINANCIAL_FILINGS"],
                        "social_media_research": ["OSINT_GENERAL", "HUMINT_NETWORK"]
                    }
                    required_atoms = method_to_atom.get(method, [])
                    if required_atoms:
                        method_match = any(atom in atoms for atom in required_atoms)
                    else:
                        # Fallback to thematic tags
                        method_match = any(method in t or t in method for t in thematic)
                else:
                    method_match = True  # No method filter

                if not method_match:
                    continue

                # Score the source
                success = methodology.get("success_rate", source.get("reliability", {}).get("success_rate", 0.5))
                friction = methodology.get("friction", "open")
                friction_penalty = {"open": 0, "restricted": -0.1, "paywalled": -0.2, "impossible": -0.5}.get(friction, 0)
                jur_bonus = 0.1 if jurisdiction and jur == jurisdiction else 0

                score = (success or 0.5) + friction_penalty + jur_bonus

                candidates.append({
                    "domain": source.get("domain", ""),
                    "name": source.get("name", source.get("domain", "")),
                    "url": source.get("url") or source.get("search_template", f"https://{source.get('domain', '')}"),
                    "success_rate": success or 0.5,
                    "friction": friction,
                    "atoms": atoms[:3],
                    "jurisdiction": jur,
                    "_score": score
                })

        # Sort by score and return top N
        candidates.sort(key=lambda x: -x["_score"])
        return candidates[:max_sources]

    async def execute_chain(
        self,
        chain: Dict[str, Any],
        executor: 'IOExecutor' = None,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """Execute a multi-step chain plan.

        Takes a chain from plan_chain() and executes each step sequentially,
        passing extracted entities to dependent steps.

        Args:
            chain: Chain plan from plan_chain()
            executor: IOExecutor instance (created if not provided)
            dry_run: If True, show what would execute without running

        Returns:
            Aggregated results from all steps
        """
        if "error" in chain:
            return chain

        if executor is None:
            executor = IOExecutor(self.router, dry_run=dry_run)

        start_time = datetime.now()
        start_value = chain["start"]["value"]
        start_type = chain["start"]["type"]
        jurisdiction = chain["start"].get("jurisdiction")

        results = {
            "chain_type": chain["chain_type"],
            "description": chain["description"],
            "start": chain["start"],
            "step_results": [],
            "extracted_entities": {"persons": [], "companies": [], "emails": [], "domains": []},
            "errors": [],
            "dry_run": dry_run
        }

        # Track current value for each entity type
        current_values = {start_type: [start_value]}

        for step in chain["steps"]:
            step_result = {
                "order": step["order"],
                "label": step["label"],
                "section": step.get("section"),
                "from_field": step["from_field"],
                "to_field": step["to_field"],
            }

            # Get sources for this step
            sources = self.select_sources(step, jurisdiction)
            step_result["sources"] = [s["name"] for s in sources[:2]]

            if dry_run:
                step_result["status"] = "would_execute"
                step_result["plan"] = f"Execute via {step['route']} using {sources[0]['name'] if sources else 'unknown'}"
            else:
                # Determine input value based on from_field
                from_code = step["from_code"]
                input_values = []

                # Map field code to entity type
                if from_code == 13:  # company_name
                    input_values = current_values.get("company", [start_value])
                elif from_code == 7:  # person_name
                    input_values = current_values.get("person", [])
                elif from_code in [71, 73, 74]:  # shareholders
                    input_values = current_values.get("shareholder", [])
                elif from_code in [58, 59]:  # officers
                    input_values = current_values.get("officer", [])
                else:
                    input_values = [start_value]

                if not input_values:
                    step_result["status"] = "skipped"
                    step_result["reason"] = f"No input values for {step['from_field']}"
                else:
                    try:
                        # Execute for first input value (could parallelize later)
                        input_val = input_values[0]

                        # Route to appropriate executor method
                        if step.get("method") == "corporate_registry_search":
                            exec_result = await executor.execute("company", input_val, jurisdiction)
                        elif step.get("method") == "osint":
                            exec_result = await executor.execute("person", input_val, jurisdiction)
                        elif step.get("method") == "sanctions_screening":
                            exec_result = await executor.execute("company", input_val, jurisdiction)
                        elif step.get("method") == "media_monitoring":
                            exec_result = await executor.execute("company", input_val, jurisdiction)
                        elif step.get("method") == "court_search":
                            exec_result = await executor.execute("company", input_val, jurisdiction)
                        else:
                            # Default to company search
                            exec_result = await executor.execute("company", input_val, jurisdiction)

                        step_result["status"] = "executed"
                        step_result["modules_run"] = exec_result.get("modules_run", [])

                        # Extract entities from results for downstream steps
                        if step.get("yields"):
                            extracted = self._extract_entities(exec_result, step["yields"])
                            if step["yields"] == "person":
                                current_values.setdefault("person", []).extend(extracted)
                                results["extracted_entities"]["persons"].extend(extracted)
                            elif step["yields"] == "company":
                                current_values.setdefault("company", []).extend(extracted)
                                results["extracted_entities"]["companies"].extend(extracted)

                        if exec_result.get("errors"):
                            step_result["errors"] = exec_result["errors"]

                    except Exception as e:
                        step_result["status"] = "error"
                        step_result["error"] = str(e)
                        results["errors"].append(f"Step {step['order']}: {str(e)}")

            results["step_results"].append(step_result)

        results["duration_seconds"] = (datetime.now() - start_time).total_seconds()
        results["steps_completed"] = len([s for s in results["step_results"] if s.get("status") in ["executed", "would_execute"]])
        results["steps_total"] = len(chain["steps"])

        return results

    def _extract_entities(self, result: Dict, entity_type: str) -> List[str]:
        """Extract entity names from execution result.

        Args:
            result: Execution result dict
            entity_type: 'person', 'company', 'email', 'domain'

        Returns:
            List of extracted entity names
        """
        entities = []

        # Check various result locations
        results = result.get("results", {})

        if entity_type == "person":
            # Look for officer names, shareholder names, etc.
            if "corporella" in results:
                officers = results["corporella"].get("officers", [])
                entities.extend([o.get("name", "") for o in officers if o.get("name")])
            if "schema_org_entities" in results:
                for e in results["schema_org_entities"]:
                    if e.get("name"):
                        entities.append(e["name"])

        elif entity_type == "company":
            # Look for related companies, shareholders
            if "corporella" in results:
                shareholders = results["corporella"].get("shareholders", [])
                for sh in shareholders:
                    if sh.get("type") == "company" and sh.get("name"):
                        entities.append(sh["name"])

        return entities[:10]  # Limit to prevent explosion

    def merge_results(self, chain_result: Dict[str, Any]) -> Dict[str, Any]:
        """Merge multi-step results into a structured report.

        Takes the raw execute_chain output and organizes it by section
        for due diligence style reports.

        Args:
            chain_result: Output from execute_chain()

        Returns:
            Structured report organized by section
        """
        if "error" in chain_result:
            return chain_result

        report = {
            "subject": chain_result["start"]["value"],
            "jurisdiction": chain_result["start"].get("jurisdiction"),
            "chain_type": chain_result["chain_type"],
            "description": chain_result["description"],
            "sections": {},
            "entities_found": chain_result.get("extracted_entities", {}),
            "summary": {
                "steps_completed": chain_result.get("steps_completed", 0),
                "steps_total": chain_result.get("steps_total", 0),
                "duration_seconds": chain_result.get("duration_seconds", 0),
                "errors": len(chain_result.get("errors", []))
            }
        }

        # Group step results by section
        for step in chain_result.get("step_results", []):
            section = step.get("section", "Other")
            if section not in report["sections"]:
                report["sections"][section] = {
                    "steps": [],
                    "status": "pending"
                }

            report["sections"][section]["steps"].append({
                "label": step["label"],
                "from": step["from_field"],
                "to": step["to_field"],
                "status": step.get("status", "unknown"),
                "sources": step.get("sources", []),
                "modules": step.get("modules_run", [])
            })

            # Update section status based on step statuses
            if step.get("status") == "executed":
                if report["sections"][section]["status"] != "partial":
                    report["sections"][section]["status"] = "complete"
            elif step.get("status") == "error":
                report["sections"][section]["status"] = "partial"
            elif step.get("status") == "skipped":
                if report["sections"][section]["status"] == "pending":
                    report["sections"][section]["status"] = "skipped"

        return report


def classify_node_type(label: str, node_type: str) -> Dict[str, Any]:
    """Classify node into specific type based on label patterns"""
    label_lower = label.lower()

    # Source nodes first (modules, APIs, databases) - rect, white
    if node_type == "source":
        return {"class": "source", "shape": "rect", "size": 1.0}

    # Person fields - circle, 2x size, green
    # Check prefix first for definite matches
    if label_lower.startswith("person_"):
        return {"class": "person", "shape": "circle", "size": 2.0}

    # Company fields - rect, 2x size, green
    # Company prefix takes priority (includes company_address, company_location, etc.)
    if label_lower.startswith("company_"):
        return {"class": "company", "shape": "rect", "size": 2.0}

    # Now check for standalone person/company keywords (not prefixed)
    if "person" in label_lower:
        return {"class": "person", "shape": "circle", "size": 2.0}
    if "company" in label_lower or "corporate" in label_lower:
        return {"class": "company", "shape": "rect", "size": 2.0}

    # Domain/URL fields - rect, white (check before address since domain can have location)
    if "domain" in label_lower or "url" in label_lower or "website" in label_lower:
        return {"class": "domain", "shape": "rect", "size": 1.0}

    # Standalone address fields - triangle, white
    # Only if not already caught by company_ or person_ prefix
    address_keywords = ["address", "location", "street", "postal", "zip", "city", "country", "region", "state"]
    if any(kw in label_lower for kw in address_keywords):
        return {"class": "address", "shape": "triangle", "size": 1.0}

    # Entity (identifiers, contact details) - rect, green
    contact_keywords = ["email", "phone", "username", "password", "mobile", "fax", "contact"]
    if any(kw in label_lower for kw in contact_keywords):
        return {"class": "entity", "shape": "rect", "size": 1.0}

    # Default entity
    return {"class": "entity", "shape": "rect", "size": 1.0}


def convert_results_to_graph(investigation_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert investigation results to graph format for visualization.

    This creates a graph showing:
    - Root node: The investigation subject (person, company, etc.)
    - Result nodes: Entities found from each module
    - Edges: Connections between subject and found entities
    """
    nodes = []
    edges = []
    node_id_counter = 0

    def make_node_id():
        nonlocal node_id_counter
        node_id_counter += 1
        return f"n{node_id_counter}"

    # Create root node for the subject
    entity_type = investigation_result.get("entity_type", "unknown")
    value = investigation_result.get("value", "Subject")
    root_id = make_node_id()

    root_class = {
        "person": "person",
        "company": "company",
        "email": "email",
        "phone": "phone",
        "domain": "domain",
    }.get(entity_type, "entity")

    nodes.append({
        "id": root_id,
        "label": value,
        "displayLabel": value,
        "type": entity_type,
        "nodeClass": root_class,
        "isRoot": True,
        "shape": "circle" if entity_type == "person" else "rect",
        "sizeMultiplier": 1.5,
    })

    results = investigation_result.get("results", {})

    # Process each module's results
    for module_name, module_results in results.items():
        if not module_results:
            continue

        # Create module group node
        module_id = make_node_id()
        nodes.append({
            "id": module_id,
            "label": module_name.upper(),
            "displayLabel": module_name.replace("_", " ").title(),
            "type": "module",
            "nodeClass": "source",
            "shape": "diamond",
            "sizeMultiplier": 0.8,
        })
        edges.append({
            "source": root_id,
            "target": module_id,
            "label": "searched_by",
        })

        # Handle different result structures
        if isinstance(module_results, list):
            # List of entities (WDC, OpenCorporates, etc.)
            for i, item in enumerate(module_results[:15]):  # Limit to 15 per module
                if isinstance(item, dict):
                    item_id = make_node_id()
                    label = item.get("name") or item.get("label") or item.get("title") or f"Result {i+1}"
                    item_type = item.get("type") or item.get("@type") or "entity"

                    # Determine class from item type
                    item_class = "entity"
                    if "person" in str(item_type).lower():
                        item_class = "person"
                    elif "company" in str(item_type).lower() or "organization" in str(item_type).lower():
                        item_class = "company"
                    elif "email" in label.lower() or "@" in label:
                        item_class = "email"
                    elif "phone" in str(item_type).lower() or item.get("telephone"):
                        item_class = "phone"

                    nodes.append({
                        "id": item_id,
                        "label": label[:50],  # Truncate long labels
                        "displayLabel": label[:50],
                        "type": item_type if isinstance(item_type, str) else "entity",
                        "nodeClass": item_class,
                        "shape": "circle" if item_class == "person" else "rect",
                        "sizeMultiplier": 1.0,
                        "data": item,  # Store full data for tooltip
                    })
                    edges.append({
                        "source": module_id,
                        "target": item_id,
                        "label": "found",
                    })

                    # Extract nested entities (email, phone, address from person/company)
                    for field in ["email", "telephone", "address", "worksFor", "jobTitle"]:
                        if field in item and item[field]:
                            nested_id = make_node_id()
                            nested_value = item[field]
                            if isinstance(nested_value, dict):
                                nested_value = nested_value.get("name") or str(nested_value)

                            nested_class = {
                                "email": "email",
                                "telephone": "phone",
                                "address": "address",
                                "worksFor": "company",
                                "jobTitle": "role",
                            }.get(field, "entity")

                            nodes.append({
                                "id": nested_id,
                                "label": str(nested_value)[:40],
                                "displayLabel": str(nested_value)[:40],
                                "type": field,
                                "nodeClass": nested_class,
                                "shape": "rect",
                                "sizeMultiplier": 0.7,
                            })
                            edges.append({
                                "source": item_id,
                                "target": nested_id,
                                "label": field,
                            })

        elif isinstance(module_results, dict):
            # Single result object (sanctions, registry_profile, etc.)
            if module_results.get("status") == "pending":
                continue  # Skip pending placeholders

            for key, value in module_results.items():
                if key in ["status", "note", "query"] or not value:
                    continue

                if isinstance(value, (str, int, float)) and value:
                    item_id = make_node_id()
                    nodes.append({
                        "id": item_id,
                        "label": f"{key}: {str(value)[:30]}",
                        "displayLabel": f"{key}: {str(value)[:30]}",
                        "type": key,
                        "nodeClass": "attribute",
                        "shape": "rect",
                        "sizeMultiplier": 0.7,
                    })
                    edges.append({
                        "source": module_id,
                        "target": item_id,
                        "label": key,
                    })
                elif isinstance(value, list) and len(value) > 0:
                    for i, item in enumerate(value[:5]):
                        item_id = make_node_id()
                        label = str(item)[:40] if isinstance(item, str) else item.get("name", f"{key}[{i}]")[:40]
                        nodes.append({
                            "id": item_id,
                            "label": label,
                            "displayLabel": label,
                            "type": key,
                            "nodeClass": "entity",
                            "shape": "rect",
                            "sizeMultiplier": 0.8,
                        })
                        edges.append({
                            "source": module_id,
                            "target": item_id,
                            "label": key,
                        })

    return {
        "nodes": nodes,
        "edges": edges,
        "center": value,
        "title": f"Investigation Results: {value}",
    }


def generate_results_viz_html(investigation_result: Dict[str, Any]) -> str:
    """Generate HTML visualization for investigation RESULTS (not source capabilities)."""

    graph_data = convert_results_to_graph(investigation_result)
    nodes = graph_data.get("nodes", [])
    edges = graph_data.get("edges", [])
    title = graph_data.get("title", "Investigation Results")

    # Color scheme for result types
    colors = {
        "person": "#22c55e",      # Green
        "company": "#8b5cf6",     # Purple
        "email": "#06b6d4",       # Cyan
        "phone": "#f59e0b",       # Amber
        "domain": "#ec4899",      # Pink
        "source": "#64748b",      # Slate (modules)
        "address": "#14b8a6",     # Teal
        "role": "#a855f7",        # Violet
        "attribute": "#94a3b8",   # Gray
        "entity": "#3b82f6",      # Blue (default)
    }

    # Minimal HTML for results visualization
    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>{title}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            background: #0a0a0f;
            font-family: ui-monospace, monospace;
            overflow: hidden;
        }}
        #header {{
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            padding: 12px 20px;
            background: rgba(10, 10, 15, 0.9);
            border-bottom: 1px solid #1e293b;
            z-index: 100;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        #header h1 {{
            color: #22c55e;
            font-size: 14px;
            font-weight: 500;
        }}
        #stats {{
            color: #64748b;
            font-size: 11px;
        }}
        #canvas {{
            position: fixed;
            top: 50px;
            left: 0;
            right: 0;
            bottom: 0;
        }}
        #legend {{
            position: fixed;
            bottom: 20px;
            left: 20px;
            background: rgba(15, 15, 20, 0.95);
            border: 1px solid #1e293b;
            border-radius: 8px;
            padding: 12px;
            font-size: 11px;
        }}
        .legend-item {{
            display: flex;
            align-items: center;
            gap: 8px;
            margin: 4px 0;
            color: #94a3b8;
        }}
        .legend-dot {{
            width: 10px;
            height: 10px;
            border-radius: 50%;
        }}
        #tooltip {{
            position: fixed;
            display: none;
            background: rgba(15, 15, 20, 0.95);
            border: 1px solid #22c55e;
            border-radius: 6px;
            padding: 10px;
            color: #e2e8f0;
            font-size: 11px;
            max-width: 300px;
            z-index: 200;
            pointer-events: none;
        }}
    </style>
</head>
<body>
    <div id="header">
        <h1>{title}</h1>
        <div id="stats">{len(nodes)} entities | {len(edges)} connections</div>
    </div>
    <canvas id="canvas"></canvas>
    <div id="legend">
        <div class="legend-item"><div class="legend-dot" style="background: {colors['person']}"></div> Person</div>
        <div class="legend-item"><div class="legend-dot" style="background: {colors['company']}"></div> Company</div>
        <div class="legend-item"><div class="legend-dot" style="background: {colors['email']}"></div> Email</div>
        <div class="legend-item"><div class="legend-dot" style="background: {colors['phone']}"></div> Phone</div>
        <div class="legend-item"><div class="legend-dot" style="background: {colors['source']}"></div> Module</div>
    </div>
    <div id="tooltip"></div>

    <script>
        const nodes = {json.dumps(nodes)};
        const edges = {json.dumps(edges)};
        const colors = {json.dumps(colors)};

        const canvas = document.getElementById('canvas');
        const ctx = canvas.getContext('2d');
        const tooltip = document.getElementById('tooltip');

        let width, height;
        let transform = {{ x: 0, y: 0, scale: 1 }};
        let dragging = null;
        let panning = false;
        let panStart = {{ x: 0, y: 0 }};

        function resize() {{
            width = canvas.width = window.innerWidth;
            height = canvas.height = window.innerHeight - 50;
            transform.x = width / 2;
            transform.y = height / 2;
            layout();
            render();
        }}

        function layout() {{
            // Simple force-directed layout
            const nodeMap = {{}};
            nodes.forEach((n, i) => {{
                if (n.isRoot) {{
                    n.x = 0;
                    n.y = 0;
                }} else {{
                    const angle = (i / nodes.length) * Math.PI * 2;
                    const radius = 150 + (i % 3) * 80;
                    n.x = Math.cos(angle) * radius;
                    n.y = Math.sin(angle) * radius;
                }}
                n.vx = 0;
                n.vy = 0;
                nodeMap[n.id] = n;
            }});

            // Run simple force simulation
            for (let iter = 0; iter < 100; iter++) {{
                // Repulsion between nodes
                for (let i = 0; i < nodes.length; i++) {{
                    for (let j = i + 1; j < nodes.length; j++) {{
                        const dx = nodes[j].x - nodes[i].x;
                        const dy = nodes[j].y - nodes[i].y;
                        const dist = Math.sqrt(dx * dx + dy * dy) || 1;
                        const force = 2000 / (dist * dist);
                        const fx = (dx / dist) * force;
                        const fy = (dy / dist) * force;
                        nodes[i].vx -= fx;
                        nodes[i].vy -= fy;
                        nodes[j].vx += fx;
                        nodes[j].vy += fy;
                    }}
                }}

                // Attraction along edges
                edges.forEach(e => {{
                    const source = nodeMap[e.source];
                    const target = nodeMap[e.target];
                    if (!source || !target) return;
                    const dx = target.x - source.x;
                    const dy = target.y - source.y;
                    const dist = Math.sqrt(dx * dx + dy * dy) || 1;
                    const force = dist * 0.01;
                    const fx = (dx / dist) * force;
                    const fy = (dy / dist) * force;
                    source.vx += fx;
                    source.vy += fy;
                    target.vx -= fx;
                    target.vy -= fy;
                }});

                // Apply velocities
                nodes.forEach(n => {{
                    if (!n.isRoot) {{
                        n.x += n.vx * 0.1;
                        n.y += n.vy * 0.1;
                    }}
                    n.vx *= 0.9;
                    n.vy *= 0.9;
                }});
            }}
        }}

        function render() {{
            ctx.clearRect(0, 0, width, height);
            ctx.save();
            ctx.translate(transform.x, transform.y);
            ctx.scale(transform.scale, transform.scale);

            const nodeMap = {{}};
            nodes.forEach(n => nodeMap[n.id] = n);

            // Draw edges
            ctx.strokeStyle = '#1e293b';
            ctx.lineWidth = 1;
            edges.forEach(e => {{
                const source = nodeMap[e.source];
                const target = nodeMap[e.target];
                if (!source || !target) return;
                ctx.beginPath();
                ctx.moveTo(source.x, source.y);
                ctx.lineTo(target.x, target.y);
                ctx.stroke();
            }});

            // Draw nodes
            nodes.forEach(n => {{
                const color = colors[n.nodeClass] || colors.entity;
                const size = (n.sizeMultiplier || 1) * 20;

                ctx.fillStyle = color;
                ctx.beginPath();
                if (n.shape === 'circle') {{
                    ctx.arc(n.x, n.y, size, 0, Math.PI * 2);
                }} else if (n.shape === 'diamond') {{
                    ctx.moveTo(n.x, n.y - size);
                    ctx.lineTo(n.x + size, n.y);
                    ctx.lineTo(n.x, n.y + size);
                    ctx.lineTo(n.x - size, n.y);
                    ctx.closePath();
                }} else {{
                    ctx.rect(n.x - size, n.y - size * 0.6, size * 2, size * 1.2);
                }}
                ctx.fill();

                // Label
                ctx.fillStyle = '#e2e8f0';
                ctx.font = '10px ui-monospace, monospace';
                ctx.textAlign = 'center';
                ctx.fillText(n.displayLabel || n.label, n.x, n.y + size + 14);
            }});

            ctx.restore();
        }}

        // Mouse handlers
        canvas.addEventListener('mousedown', e => {{
            const mx = (e.clientX - transform.x) / transform.scale;
            const my = (e.clientY - 50 - transform.y) / transform.scale;

            for (const n of nodes) {{
                const dx = mx - n.x;
                const dy = my - n.y;
                if (Math.sqrt(dx*dx + dy*dy) < 25) {{
                    dragging = n;
                    return;
                }}
            }}
            panning = true;
            panStart = {{ x: e.clientX, y: e.clientY }};
        }});

        canvas.addEventListener('mousemove', e => {{
            if (dragging) {{
                dragging.x = (e.clientX - transform.x) / transform.scale;
                dragging.y = (e.clientY - 50 - transform.y) / transform.scale;
                render();
            }} else if (panning) {{
                transform.x += e.clientX - panStart.x;
                transform.y += e.clientY - panStart.y;
                panStart = {{ x: e.clientX, y: e.clientY }};
                render();
            }} else {{
                // Hover tooltip
                const mx = (e.clientX - transform.x) / transform.scale;
                const my = (e.clientY - 50 - transform.y) / transform.scale;

                let hovered = null;
                for (const n of nodes) {{
                    const dx = mx - n.x;
                    const dy = my - n.y;
                    if (Math.sqrt(dx*dx + dy*dy) < 25) {{
                        hovered = n;
                        break;
                    }}
                }}

                if (hovered) {{
                    tooltip.style.display = 'block';
                    tooltip.style.left = (e.clientX + 15) + 'px';
                    tooltip.style.top = (e.clientY + 15) + 'px';
                    let html = `<strong>${{hovered.displayLabel}}</strong><br>Type: ${{hovered.type}}`;
                    if (hovered.data) {{
                        const data = hovered.data;
                        if (data.telephone) html += `<br>Phone: ${{data.telephone}}`;
                        if (data.email) html += `<br>Email: ${{data.email}}`;
                        if (data.worksFor) html += `<br>Works For: ${{data.worksFor}}`;
                        if (data.url) html += `<br>URL: ${{data.url}}`;
                    }}
                    tooltip.innerHTML = html;
                }} else {{
                    tooltip.style.display = 'none';
                }}
            }}
        }});

        canvas.addEventListener('mouseup', () => {{
            dragging = null;
            panning = false;
        }});

        canvas.addEventListener('wheel', e => {{
            e.preventDefault();
            const factor = e.deltaY > 0 ? 0.9 : 1.1;
            transform.scale *= factor;
            transform.scale = Math.max(0.1, Math.min(5, transform.scale));
            render();
        }});

        window.addEventListener('resize', resize);
        resize();
    </script>
</body>
</html>"""

    return html


def generate_viz_html(graph_data: Dict[str, Any], router: 'IORouter') -> str:
    """Generate interactive HTML visualization matching main app styling"""
    nodes = graph_data.get("nodes", [])
    edges = graph_data.get("edges", [])
    center = graph_data.get("center", "Graph")

    # Classify each node (skip if already classified)
    for node in nodes:
        if "nodeClass" not in node:
            classification = classify_node_type(node.get("label", ""), node.get("type", "entity"))
            node["nodeClass"] = classification["class"]
            node["shape"] = classification["shape"]
            node["sizeMultiplier"] = classification["size"]
        # Support displayLabel for clean names while keeping classification separate
        if "displayLabel" not in node:
            node["displayLabel"] = node.get("label", "")

    # Color scheme
    colors = {
        "person": {"bg": "#16a34a", "border": "#15803d", "text": "#FFFFFF"},
        "company": {"bg": "#16a34a", "border": "#15803d", "text": "#FFFFFF"},
        "entity": {"bg": "#16a34a", "border": "#15803d", "text": "#FFFFFF"},
        "source": {"bg": "#FFFFFF", "border": "#d1d5db", "text": "#000000"},
        "address": {"bg": "#FFFFFF", "border": "#d1d5db", "text": "#000000"},
        "domain": {"bg": "#FFFFFF", "border": "#d1d5db", "text": "#000000"},
        "record": {"bg": "#FFFFFF", "border": "#d1d5db", "text": "#000000"},
    }
    surface_bg = "#0f172a"

    nodes_json = json.dumps(nodes)
    edges_json = json.dumps(edges)

    # Prepare simplified routing data for client-side chain reaction
    # Group rules by input code, only keep top sources per input
    routing_data = {}
    for node in nodes:
        if node.get("type") == "entity":
            node_id = node["id"]
            if isinstance(node_id, int):
                # Find sources for this entity
                sources_for_node = {}
                for rule in router.rules if hasattr(router, 'rules') else []:
                    requires = rule.get("requires_any", rule.get("inputs", []))
                    returns = rule.get("returns", rule.get("outputs", []))
                    if node_id in requires:
                        label = rule.get("label", rule.get("source", ""))
                        if label.startswith("BLOCKED") or label.startswith("'''") or len(label) < 3:
                            continue
                        if label not in sources_for_node:
                            sources_for_node[label] = set()
                        for out in returns:
                            sources_for_node[label].add(out)
                # Keep top 10 sources
                top = sorted(sources_for_node.items(), key=lambda x: -len(x[1]))[:10]
                if top:
                    routing_data[node_id] = {label: list(outs) for label, outs in top}

    routing_json = json.dumps(routing_data)

    html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>IO Matrix - {center}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: Inter, system-ui, -apple-system, sans-serif;
            background: {surface_bg};
            color: #e2e8f0;
            overflow: hidden;
        }}
        #container {{
            width: 100vw;
            height: 100vh;
            position: relative;
        }}
        #controls {{
            position: absolute;
            top: 16px;
            left: 16px;
            z-index: 100;
            background: rgba(30, 41, 59, 0.95);
            padding: 16px;
            border-radius: 8px;
            border: 1px solid #334155;
            display: flex;
            flex-direction: column;
            gap: 12px;
            min-width: 220px;
            max-height: calc(100vh - 100px);
            overflow-y: auto;
        }}
        #controls h3 {{
            font-size: 14px;
            font-weight: 600;
            color: #94a3b8;
            margin-bottom: 4px;
        }}
        #controls h4 {{
            font-size: 12px;
            font-weight: 600;
            color: #64748b;
            margin-top: 8px;
            margin-bottom: 4px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        #controls label {{
            font-size: 12px;
            color: #94a3b8;
        }}
        #spacing-slider {{
            width: 100%;
            cursor: pointer;
        }}
        #spacing-value {{
            font-size: 11px;
            color: #64748b;
        }}
        .btn {{
            padding: 8px 12px;
            border: 1px solid #475569;
            background: #1e293b;
            color: #e2e8f0;
            border-radius: 6px;
            cursor: pointer;
            font-size: 12px;
            transition: all 0.2s;
        }}
        .btn:hover {{
            background: #334155;
            border-color: #64748b;
        }}
        .btn-row {{
            display: flex;
            gap: 8px;
        }}
        .filter-row {{
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 4px 0;
        }}
        .filter-row input[type="checkbox"] {{
            width: 16px;
            height: 16px;
            cursor: pointer;
        }}
        .filter-row label {{
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 6px;
        }}
        .filter-icon {{
            width: 14px;
            height: 14px;
            border: 2px solid;
            display: inline-block;
        }}
        .filter-icon.circle {{ border-radius: 50%; }}
        .filter-icon.triangle {{
            width: 0;
            height: 0;
            border-left: 7px solid transparent;
            border-right: 7px solid transparent;
            border-bottom: 12px solid;
            background: transparent !important;
        }}
        .filter-icon.rect {{ border-radius: 2px; }}
        #canvas {{
            width: 100%;
            height: 100%;
        }}
        #tooltip {{
            position: absolute;
            background: rgba(30, 41, 59, 0.98);
            border: 1px solid #475569;
            border-radius: 6px;
            padding: 10px 14px;
            font-size: 13px;
            color: #e2e8f0;
            max-width: 400px;
            word-wrap: break-word;
            pointer-events: none;
            display: none;
            z-index: 200;
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        }}
        #log-panel {{
            position: absolute;
            top: 16px;
            right: 16px;
            width: 280px;
            max-height: 200px;
            background: rgba(30, 41, 59, 0.95);
            border: 1px solid #334155;
            border-radius: 8px;
            font-size: 11px;
            z-index: 100;
            overflow: hidden;
        }}
        #log-header {{
            padding: 8px 12px;
            background: #1e293b;
            color: #94a3b8;
            font-weight: 600;
            border-bottom: 1px solid #334155;
        }}
        #log-content {{
            padding: 8px 12px;
            max-height: 160px;
            overflow-y: auto;
            font-family: monospace;
            color: #64748b;
        }}
        #log-content div {{
            padding: 2px 0;
            border-bottom: 1px solid #1e293b;
        }}
        #log-content div:last-child {{
            border-bottom: none;
        }}
        .log-info {{ color: #38bdf8; }}
        .log-success {{ color: #4ade80; }}
        .log-action {{ color: #fbbf24; }}
        #legend {{
            position: absolute;
            bottom: 16px;
            left: 16px;
            background: rgba(30, 41, 59, 0.95);
            padding: 12px 16px;
            border-radius: 8px;
            border: 1px solid #334155;
            display: flex;
            flex-wrap: wrap;
            gap: 16px;
            font-size: 12px;
            max-width: 600px;
        }}
        .legend-item {{
            display: flex;
            align-items: center;
            gap: 6px;
        }}
        .legend-shape {{
            display: inline-block;
        }}
        .legend-shape.circle {{
            width: 14px;
            height: 14px;
            border-radius: 50%;
            border: 2px solid;
        }}
        .legend-shape.triangle {{
            width: 0;
            height: 0;
            border-left: 7px solid transparent;
            border-right: 7px solid transparent;
            border-bottom: 12px solid #FFFFFF;
        }}
        .legend-shape.rect {{
            width: 14px;
            height: 10px;
            border-radius: 2px;
            border: 2px solid;
        }}
    </style>
</head>
<body>
    <div id="container">
        <svg id="canvas"></svg>
        <div id="controls">
            <h3>IO Matrix: {center}</h3>
            <div>
                <label>Node Spacing</label>
                <input type="range" id="spacing-slider" min="50" max="500" value="100">
                <span id="spacing-value">100%</span>
            </div>
            <div class="btn-row">
                <button class="btn" id="fit-btn">Fit All</button>
                <button class="btn" id="reset-btn">Reset</button>
            </div>
            <div class="btn-row">
                <button class="btn" id="frontier-btn">Show Unexplored</button>
            </div>
            <div id="frontier-info" style="font-size: 11px; color: #94a3b8; margin-top: 4px; display: none;">
                <span id="frontier-count">0</span> nodes have more sources to explore
            </div>
            <h4>Filter by Type</h4>
            <div class="filter-row">
                <input type="checkbox" id="filter-person" checked>
                <label for="filter-person">
                    <span class="filter-icon circle" style="background: #16a34a; border-color: #15803d;"></span>
                    Person (2x)
                </label>
            </div>
            <div class="filter-row">
                <input type="checkbox" id="filter-company" checked>
                <label for="filter-company">
                    <span class="filter-icon rect" style="background: #16a34a; border-color: #15803d;"></span>
                    Company (2x)
                </label>
            </div>
            <div class="filter-row">
                <input type="checkbox" id="filter-entity" checked>
                <label for="filter-entity">
                    <span class="filter-icon rect" style="background: #16a34a; border-color: #15803d;"></span>
                    Entity
                </label>
            </div>
            <div class="filter-row">
                <input type="checkbox" id="filter-source" checked>
                <label for="filter-source">
                    <span class="filter-icon rect" style="background: #FFFFFF; border-color: #d1d5db;"></span>
                    Source/Module
                </label>
            </div>
            <div class="filter-row">
                <input type="checkbox" id="filter-domain" checked>
                <label for="filter-domain">
                    <span class="filter-icon rect" style="background: #FFFFFF; border-color: #d1d5db;"></span>
                    Domain/URL
                </label>
            </div>
            <div class="filter-row">
                <input type="checkbox" id="filter-address" checked>
                <label for="filter-address">
                    <span class="filter-icon triangle" style="border-bottom-color: #FFFFFF;"></span>
                    Address
                </label>
            </div>
            <h4>Run IO on Type</h4>
            <div class="btn-row" style="flex-wrap: wrap; gap: 6px;">
                <button class="btn run-type-btn" data-type="person" style="font-size: 11px; padding: 6px 10px;">Person</button>
                <button class="btn run-type-btn" data-type="company" style="font-size: 11px; padding: 6px 10px;">Company</button>
                <button class="btn run-type-btn" data-type="entity" style="font-size: 11px; padding: 6px 10px;">Entity</button>
                <button class="btn run-type-btn" data-type="domain" style="font-size: 11px; padding: 6px 10px;">Domain</button>
                <button class="btn run-type-btn" data-type="address" style="font-size: 11px; padding: 6px 10px;">Address</button>
            </div>
            <div id="run-type-info" style="font-size: 10px; color: #64748b; margin-top: 4px;">
                Click to run IO Matrix on all unexplored nodes of that type
            </div>
        </div>
        <div id="tooltip"></div>
        <div id="log-panel">
            <div id="log-header">Progress Log</div>
            <div id="log-content"></div>
        </div>
        <div id="legend">
            <div class="legend-item">
                <span class="legend-shape circle" style="background: #16a34a; border-color: #15803d;"></span>
                <span>Person (2x)</span>
            </div>
            <div class="legend-item">
                <span class="legend-shape rect" style="background: #16a34a; border-color: #15803d; width: 20px;"></span>
                <span>Company (2x)</span>
            </div>
            <div class="legend-item">
                <span class="legend-shape rect" style="background: #16a34a; border-color: #15803d;"></span>
                <span>Entity</span>
            </div>
            <div class="legend-item">
                <span class="legend-shape rect" style="background: #FFFFFF; border-color: #d1d5db;"></span>
                <span>Source/Module</span>
            </div>
            <div class="legend-item">
                <span class="legend-shape rect" style="background: #FFFFFF; border-color: #d1d5db;"></span>
                <span>Domain</span>
            </div>
            <div class="legend-item">
                <span class="legend-shape triangle"></span>
                <span>Address</span>
            </div>
        </div>
    </div>
    <script>
    (function() {{
        let nodes = {nodes_json};
        let edges = {edges_json};
        const colors = {json.dumps(colors)};
        const routingData = {routing_json};
        const legend = {json.dumps(router.legend)};

        // Logging function
        const logContent = document.getElementById('log-content');
        function log(msg, type = 'info') {{
            const div = document.createElement('div');
            div.className = 'log-' + type;
            div.textContent = new Date().toLocaleTimeString().slice(0,5) + ' ' + msg;
            logContent.appendChild(div);
            logContent.scrollTop = logContent.scrollHeight;
            // Keep only last 20 logs
            while (logContent.children.length > 20) {{
                logContent.removeChild(logContent.firstChild);
            }}
        }}

        log('Loaded ' + nodes.length + ' nodes, ' + edges.length + ' edges', 'success');

        // Node classification helper (mirrors Python classify_node_type)
        function classifyNode(label, nodeType) {{
            const l = label.toLowerCase();
            // Source nodes first
            if (nodeType === 'source') return {{ class: 'source', shape: 'rect', size: 1.0 }};
            // Person prefix takes priority
            if (l.startsWith('person_')) return {{ class: 'person', shape: 'circle', size: 2.0 }};
            // Company prefix takes priority (includes company_address, etc.)
            if (l.startsWith('company_')) return {{ class: 'company', shape: 'rect', size: 2.0 }};
            // Standalone person/company keywords
            if (l.includes('person')) return {{ class: 'person', shape: 'circle', size: 2.0 }};
            if (l.includes('company') || l.includes('corporate')) return {{ class: 'company', shape: 'rect', size: 2.0 }};
            // Domain before address
            if (l.includes('domain') || l.includes('url') || l.includes('website')) return {{ class: 'domain', shape: 'rect', size: 1.0 }};
            // Standalone address fields only
            const addressKw = ['address', 'location', 'street', 'postal', 'zip', 'city', 'country', 'region', 'state'];
            if (addressKw.some(kw => l.includes(kw))) return {{ class: 'address', shape: 'triangle', size: 1.0 }};
            // Contact keywords
            const contactKw = ['email', 'phone', 'username', 'password', 'mobile', 'fax', 'contact'];
            if (contactKw.some(kw => l.includes(kw))) return {{ class: 'entity', shape: 'rect', size: 1.0 }};
            return {{ class: 'entity', shape: 'rect', size: 1.0 }};
        }}

        const svg = document.getElementById('canvas');
        const tooltip = document.getElementById('tooltip');
        const spacingSlider = document.getElementById('spacing-slider');
        const spacingValue = document.getElementById('spacing-value');
        const fitBtn = document.getElementById('fit-btn');
        const resetBtn = document.getElementById('reset-btn');
        const frontierBtn = document.getElementById('frontier-btn');
        const frontierInfo = document.getElementById('frontier-info');
        const frontierCount = document.getElementById('frontier-count');

        // Filter checkboxes
        const filters = {{
            person: document.getElementById('filter-person'),
            company: document.getElementById('filter-company'),
            entity: document.getElementById('filter-entity'),
            source: document.getElementById('filter-source'),
            domain: document.getElementById('filter-domain'),
            address: document.getElementById('filter-address')
        }};

        let transform = {{ x: 0, y: 0, scale: 1 }};
        let isDragging = false;
        let dragStart = {{ x: 0, y: 0 }};
        let spacingMultiplier = 1;
        let nodePositions = {{}};
        let expandedNodes = new Set();
        let hiddenClasses = new Set();
        let showFrontier = false;

        // Count frontier nodes
        const frontierNodes = nodes.filter(n => n.frontier === true);
        if (frontierCount) frontierCount.textContent = frontierNodes.length;

        // Node selection and dragging state
        let selectedNodeId = null;
        let isDraggingNode = false;
        let nodeDragStart = {{ x: 0, y: 0 }};
        let nodeDragStartTime = 0;
        let groupDragMode = false;
        const GROUP_DRAG_DELAY = 1000; // 1 second hold for group drag

        // Get connected nodes for a given node
        function getConnectedNodes(nodeId) {{
            const connected = new Set();
            edges.forEach(e => {{
                if (e.from === nodeId) connected.add(e.to);
                if (e.to === nodeId) connected.add(e.from);
            }});
            return connected;
        }}

        // Get connected edges for a given node
        function getConnectedEdges(nodeId) {{
            return edges.filter(e => e.from === nodeId || e.to === nodeId);
        }}

        // Lightweight position update (no full re-render)
        function updatePositions() {{
            const mainGroup = svg.querySelector('g');
            if (!mainGroup) return;

            // Update node positions via transform
            svg.querySelectorAll('.node').forEach(node => {{
                const id = node.dataset.id;
                const pos = nodePositions[id];
                if (!pos) return;

                // Find the shape element and update its position
                const circle = node.querySelector('circle');
                const rect = node.querySelector('rect');
                const polygon = node.querySelector('polygon');
                const text = node.querySelector('text');

                if (circle) {{
                    circle.setAttribute('cx', pos.x);
                    circle.setAttribute('cy', pos.y);
                }}
                if (rect) {{
                    const width = parseFloat(rect.getAttribute('width'));
                    const height = parseFloat(rect.getAttribute('height'));
                    rect.setAttribute('x', pos.x - width/2);
                    rect.setAttribute('y', pos.y - height/2);
                }}
                if (polygon) {{
                    // Recalculate triangle points
                    const n = nodes.find(n => String(n.id) === String(id));
                    if (n) {{
                        const sizeMultiplier = n.sizeMultiplier || 1;
                        const h = BASE_NODE_HEIGHT * sizeMultiplier * 1.2;
                        const w = BASE_NODE_WIDTH * sizeMultiplier * 0.8;
                        const points = [
                            pos.x + ',' + (pos.y - h/2),
                            (pos.x - w/2) + ',' + (pos.y + h/2),
                            (pos.x + w/2) + ',' + (pos.y + h/2)
                        ].join(' ');
                        polygon.setAttribute('points', points);
                    }}
                }}
                if (text) {{
                    text.setAttribute('x', pos.x);
                    const fontSize = parseFloat(text.getAttribute('font-size')) || 12;
                    text.setAttribute('y', pos.y + fontSize/3);
                }}
            }});

            // Update edge positions
            const visibleNodeIds = getVisibleNodeIdSet();
            const lines = mainGroup.querySelectorAll('line');
            let lineIndex = 0;

            const edgeCounts = {{}};
            edges.forEach(e => {{
                if (!visibleNodeIds.has(String(e.from)) || !visibleNodeIds.has(String(e.to))) return;
                const key = [e.from, e.to].sort().join('-');
                edgeCounts[key] = (edgeCounts[key] || 0) + 1;
            }});
            const edgeIndex = {{}};

            edges.forEach(e => {{
                if (!visibleNodeIds.has(String(e.from)) || !visibleNodeIds.has(String(e.to))) return;
                const from = nodePositions[e.from];
                const to = nodePositions[e.to];
                if (!from || !to) return;

                const key = [e.from, e.to].sort().join('-');
                const idx = edgeIndex[key] || 0;
                edgeIndex[key] = idx + 1;
                const count = edgeCounts[key];
                const offset = (idx - (count - 1) / 2) * 8;

                const dx = to.x - from.x;
                const dy = to.y - from.y;
                const len = Math.sqrt(dx*dx + dy*dy) || 1;
                const nx = -dy / len * offset;
                const ny = dx / len * offset;

                if (lines[lineIndex]) {{
                    lines[lineIndex].setAttribute('x1', from.x + nx);
                    lines[lineIndex].setAttribute('y1', from.y + ny);
                    lines[lineIndex].setAttribute('x2', to.x + nx);
                    lines[lineIndex].setAttribute('y2', to.y + ny);
                }}
                lineIndex++;
            }});
        }}

        // Layout parameters
        const BASE_NODE_WIDTH = 200;
        const BASE_NODE_HEIGHT = 50;
        const BASE_SPACING = 250;

        // Force-directed clustering layout
        function computeLayout() {{
            const nodeCount = nodes.length;
            if (nodeCount === 0) return;

            const spacing = BASE_SPACING * spacingMultiplier;

            // Cluster layout: SOURCE nodes are cluster centers, entities orbit around them
            // Build adjacency map
            const adjacency = {{}};
            nodes.forEach(n => {{ adjacency[n.id] = new Set(); }});
            edges.forEach(e => {{
                if (adjacency[e.from]) adjacency[e.from].add(e.to);
                if (adjacency[e.to]) adjacency[e.to].add(e.from);
            }});

            // Find source nodes (they become cluster centers)
            const sourceNodes = nodes.filter(n => n.type === 'source' || String(n.id).startsWith('src_'));
            const entityNodes = nodes.filter(n => n.type !== 'source' && !String(n.id).startsWith('src_'));

            // Each source forms a cluster with its directly connected entities
            const clusters = [];
            const nodeToCluster = {{}};
            const assignedEntities = new Set();

            sourceNodes.forEach((src, si) => {{
                const cluster = {{ center: src.id, members: [src.id] }};
                const neighbors = adjacency[src.id] || new Set();
                neighbors.forEach(neighborId => {{
                    // Only add entities not yet assigned to a cluster
                    const neighborNode = nodes.find(n => n.id === neighborId);
                    if (neighborNode && neighborNode.type !== 'source' && !String(neighborId).startsWith('src_')) {{
                        if (!assignedEntities.has(neighborId)) {{
                            cluster.members.push(neighborId);
                            assignedEntities.add(neighborId);
                        }}
                    }}
                }});
                nodeToCluster[src.id] = si;
                cluster.members.forEach(id => {{ nodeToCluster[id] = si; }});
                clusters.push(cluster);
            }});

            // Any unassigned entities go into their own mini-clusters or nearest source
            entityNodes.forEach(entity => {{
                if (!assignedEntities.has(entity.id)) {{
                    // Find which sources this entity connects to
                    const neighbors = adjacency[entity.id] || new Set();
                    let nearestCluster = -1;
                    neighbors.forEach(neighborId => {{
                        if (nodeToCluster[neighborId] !== undefined && nearestCluster === -1) {{
                            nearestCluster = nodeToCluster[neighborId];
                        }}
                    }});
                    if (nearestCluster >= 0) {{
                        clusters[nearestCluster].members.push(entity.id);
                        nodeToCluster[entity.id] = nearestCluster;
                    }} else {{
                        // Orphan - create its own cluster
                        const ci = clusters.length;
                        clusters.push({{ center: entity.id, members: [entity.id] }});
                        nodeToCluster[entity.id] = ci;
                    }}
                }}
            }});

            // Position clusters scattered across the canvas
            const clusterCenters = [];
            const goldenAngle = Math.PI * (3 - Math.sqrt(5));
            const clusterCount = clusters.length;
            const baseRadius = spacing * Math.sqrt(clusterCount) * 2;

            clusters.forEach((cluster, ci) => {{
                // Spiral placement
                const angle = ci * goldenAngle * 2.5;
                const radius = baseRadius * (0.3 + 0.7 * Math.sqrt((ci + 1) / clusterCount));
                const cx = Math.cos(angle) * radius;
                const cy = Math.sin(angle) * radius;
                clusterCenters.push({{ x: cx, y: cy }});

                // Position center node
                nodePositions[cluster.center] = {{ x: cx, y: cy }};

                // Position member nodes around center
                const members = cluster.members.filter(id => id !== cluster.center);
                const memberCount = members.length;
                if (memberCount > 0) {{
                    const orbitRadius = spacing * 0.6 * Math.max(1, Math.sqrt(memberCount / 3));
                    members.forEach((id, i) => {{
                        const angle = (i / memberCount) * 2 * Math.PI + ci * 0.5;
                        // Vary radius slightly for organic feel
                        const r = orbitRadius * (0.7 + 0.3 * ((i % 3) / 2));
                        nodePositions[id] = {{
                            x: cx + Math.cos(angle) * r,
                            y: cy + Math.sin(angle) * r
                        }};
                    }});
                }}
            }});

            // Find shared entities (connect multiple clusters) and reposition them between
            entityNodes.forEach(entity => {{
                const neighbors = adjacency[entity.id] || new Set();
                const connectedClusters = new Set();
                neighbors.forEach(neighborId => {{
                    if (nodeToCluster[neighborId] !== undefined) {{
                        connectedClusters.add(nodeToCluster[neighborId]);
                    }}
                }});

                if (connectedClusters.size > 1) {{
                    // This entity connects multiple clusters - position between them
                    let avgX = 0, avgY = 0, count = 0;
                    connectedClusters.forEach(ci => {{
                        avgX += clusterCenters[ci].x;
                        avgY += clusterCenters[ci].y;
                        count++;
                    }});
                    if (count > 0) {{
                        nodePositions[entity.id] = {{
                            x: avgX / count,
                            y: avgY / count
                        }};
                    }}
                }}
            }});

            // Center
            let sumX = 0, sumY = 0;
            nodes.forEach(n => {{ sumX += nodePositions[n.id].x; sumY += nodePositions[n.id].y; }});
            const centerX = sumX / nodeCount, centerY = sumY / nodeCount;
            nodes.forEach(n => {{ nodePositions[n.id].x -= centerX; nodePositions[n.id].y -= centerY; }});
        }}

        function truncateText(text, maxLen = 40) {{
            // NO TRUNCATION - return full text always
            return {{ text: text, truncated: false }};
        }}

        // Wrap text into multiple lines
        function wrapText(text, maxChars = 20) {{
            if (text.length <= maxChars) return [text];
            const words = text.split(/[\\s_-]+/);
            const lines = [];
            let currentLine = '';
            words.forEach(word => {{
                if (currentLine.length + word.length + 1 <= maxChars) {{
                    currentLine = currentLine ? currentLine + ' ' + word : word;
                }} else {{
                    if (currentLine) lines.push(currentLine);
                    currentLine = word;
                }}
            }});
            if (currentLine) lines.push(currentLine);
            return lines.length > 0 ? lines : [text];
        }}

        function isNodeVisible(n) {{
            const nodeClass = n.nodeClass || 'entity';
            const visible = !hiddenClasses.has(nodeClass);
            return visible;
        }}

        function getVisibleNodes() {{
            return nodes.filter(isNodeVisible);
        }}

        // Build set of visible node IDs with consistent string keys
        function getVisibleNodeIdSet() {{
            const idSet = new Set();
            getVisibleNodes().forEach(n => {{
                idSet.add(String(n.id));
            }});
            return idSet;
        }}

        function render() {{
            const width = svg.clientWidth;
            const height = svg.clientHeight;
            const visibleNodes = getVisibleNodes();
            const visibleNodeIds = getVisibleNodeIdSet();  // Use string-consistent set

            let html = '<defs>';
            html += '<marker id="arrow" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto"><polygon points="0 0, 10 3.5, 0 7" fill="#64748b"/></marker>';
            html += '</defs>';

            // Transform group
            html += '<g transform="translate(' + (width/2 + transform.x) + ',' + (height/2 + transform.y) + ') scale(' + transform.scale + ')">';

            // Count edges between same pairs for offset calculation
            const edgeCounts = {{}};
            edges.forEach(e => {{
                if (!visibleNodeIds.has(String(e.from)) || !visibleNodeIds.has(String(e.to))) return;
                const key = [e.from, e.to].sort().join('-');
                edgeCounts[key] = (edgeCounts[key] || 0) + 1;
            }});
            const edgeIndex = {{}};

            // Get highlighted nodes (selected + connected)
            const highlightedNodes = new Set();
            if (selectedNodeId) {{
                highlightedNodes.add(selectedNodeId);
                getConnectedNodes(selectedNodeId).forEach(id => highlightedNodes.add(id));
            }}

            // Draw edges with spacing (only between visible nodes)
            edges.forEach(e => {{
                if (!visibleNodeIds.has(String(e.from)) || !visibleNodeIds.has(String(e.to))) return;
                const from = nodePositions[e.from];
                const to = nodePositions[e.to];
                if (!from || !to) return;

                const key = [e.from, e.to].sort().join('-');
                const idx = edgeIndex[key] || 0;
                edgeIndex[key] = idx + 1;
                const count = edgeCounts[key];
                const offset = (idx - (count - 1) / 2) * 8;

                // Calculate perpendicular offset
                const dx = to.x - from.x;
                const dy = to.y - from.y;
                const len = Math.sqrt(dx*dx + dy*dy) || 1;
                const nx = -dy / len * offset;
                const ny = dx / len * offset;

                const x1 = from.x + nx;
                const y1 = from.y + ny;
                const x2 = to.x + nx;
                const y2 = to.y + ny;

                // Highlight edges connected to selected node
                const isHighlighted = selectedNodeId && (e.from === selectedNodeId || e.to === selectedNodeId);
                const strokeColor = isHighlighted ? '#f59e0b' : '#475569';
                const strokeWidth = isHighlighted ? 3 : 1.5;

                html += '<line x1="' + x1 + '" y1="' + y1 + '" x2="' + x2 + '" y2="' + y2 + '" stroke="' + strokeColor + '" stroke-width="' + strokeWidth + '" marker-end="url(#arrow)"/>';
            }});

            // Draw nodes with different shapes and sizes
            visibleNodes.forEach(n => {{
                const pos = nodePositions[n.id];
                if (!pos) return;

                const nodeClass = n.nodeClass || 'entity';
                const shape = n.shape || 'rect';
                const sizeMultiplier = n.sizeMultiplier || 1;
                const color = colors[nodeClass] || colors.entity;
                const displayText = n.displayLabel || n.label;

                // Wrap text into multiple lines (max chars depends on size)
                const maxCharsPerLine = Math.round(18 * sizeMultiplier);
                const textLines = wrapText(displayText, maxCharsPerLine);
                const lineCount = textLines.length;

                // Fixed large font for person nodes, scaled for others
                let fontSize;
                if (nodeClass === 'person') {{
                    fontSize = 32;  // Fixed large size for all persons
                }} else if (nodeClass === 'company') {{
                    fontSize = 28;  // Fixed size for companies
                }} else {{
                    fontSize = Math.round(16 * sizeMultiplier);
                }}
                const lineHeight = fontSize * 1.15;
                const fontWeight = 'bold';

                // Size node to fit text
                const longestLine = Math.max(...textLines.map(l => l.length));
                const nodeWidth = Math.max(BASE_NODE_WIDTH, longestLine * fontSize * 0.6 + 40) * sizeMultiplier;
                const nodeHeight = Math.max(BASE_NODE_HEIGHT, lineCount * lineHeight + 20) * sizeMultiplier;

                // Highlight selected and connected nodes
                const isSelected = n.id === selectedNodeId;
                const isConnected = highlightedNodes.has(n.id) && !isSelected;
                const isFrontier = showFrontier && n.frontier === true;
                let strokeColor = isSelected ? '#f59e0b' : (isConnected ? '#fbbf24' : color.border);
                let strokeWidth = isSelected ? 4 : (isConnected ? 3 : 2);
                let glowFilter = isSelected ? 'filter: drop-shadow(0 0 8px #f59e0b);' : (isConnected ? 'filter: drop-shadow(0 0 4px #fbbf24);' : '');

                // Frontier nodes get magenta pulsing glow
                if (isFrontier && !isSelected) {{
                    strokeColor = '#ec4899';
                    strokeWidth = 3;
                    glowFilter = 'filter: drop-shadow(0 0 6px #ec4899);';
                }}

                html += '<g class="node" data-id="' + n.id + '" data-label="' + n.label.replace(/"/g, '&quot;') + '" data-class="' + nodeClass + '" data-frontier="' + (n.frontier ? 'true' : 'false') + '" style="' + glowFilter + '">';

                if (shape === 'circle') {{
                    // Person nodes - circle shape
                    const radius = Math.max(nodeWidth, nodeHeight) / 2;
                    html += '<circle cx="' + pos.x + '" cy="' + pos.y + '" r="' + radius + '" fill="' + color.bg + '" stroke="' + strokeColor + '" stroke-width="' + strokeWidth + '" style="cursor:pointer;"/>';
                }} else if (shape === 'triangle') {{
                    // Address nodes - triangle shape (tall enough for text)
                    const h = Math.max(nodeHeight * 2.5, lineCount * lineHeight + 60);
                    const w = nodeWidth * 1.2;
                    const points = [
                        (pos.x) + ',' + (pos.y - h/2),
                        (pos.x - w/2) + ',' + (pos.y + h/2),
                        (pos.x + w/2) + ',' + (pos.y + h/2)
                    ].join(' ');
                    html += '<polygon points="' + points + '" fill="' + color.bg + '" stroke="' + strokeColor + '" stroke-width="' + strokeWidth + '" style="cursor:pointer;"/>';
                }} else {{
                    // Default rect shape - size to fit wrapped text
                    const x = pos.x - nodeWidth / 2;
                    const y = pos.y - nodeHeight / 2;
                    html += '<rect x="' + x + '" y="' + y + '" width="' + nodeWidth + '" height="' + nodeHeight + '" rx="6" fill="' + color.bg + '" stroke="' + strokeColor + '" stroke-width="' + strokeWidth + '" style="cursor:pointer;"/>';
                }}

                // Draw multi-line text
                const textStartY = pos.y - ((lineCount - 1) * lineHeight) / 2 + fontSize / 3;
                textLines.forEach((line, i) => {{
                    const lineY = textStartY + i * lineHeight;
                    html += '<text x="' + pos.x + '" y="' + lineY + '" text-anchor="middle" fill="' + color.text + '" font-size="' + fontSize + '" font-weight="' + fontWeight + '" font-family="Inter, system-ui, sans-serif" style="pointer-events:none;">' + line + '</text>';
                }});

                html += '</g>';
            }});

            html += '</g>';
            svg.innerHTML = html;

            // Add event listeners to nodes
            svg.querySelectorAll('.node').forEach(node => {{
                node.addEventListener('mouseenter', (e) => {{
                    const label = node.dataset.label;
                    const nodeClass = node.dataset.class;
                    tooltip.innerHTML = '<strong>' + nodeClass.toUpperCase() + '</strong><br>' + label;
                    tooltip.style.display = 'block';
                    tooltip.style.left = (e.clientX + 15) + 'px';
                    tooltip.style.top = (e.clientY + 15) + 'px';
                }});
                node.addEventListener('mousemove', (e) => {{
                    if (!isDraggingNode) {{
                        tooltip.style.left = (e.clientX + 15) + 'px';
                        tooltip.style.top = (e.clientY + 15) + 'px';
                    }}
                }});
                node.addEventListener('mouseleave', () => {{
                    tooltip.style.display = 'none';
                }});

                // Node selection and drag start
                node.addEventListener('mousedown', (e) => {{
                    e.stopPropagation();
                    const id = node.dataset.id;

                    // Select the node
                    selectedNodeId = id;
                    isDraggingNode = true;
                    nodeDragStartTime = Date.now();
                    groupDragMode = false;

                    // Get mouse position in graph coordinates
                    const rect = svg.getBoundingClientRect();
                    const mx = (e.clientX - rect.left - rect.width/2 - transform.x) / transform.scale;
                    const my = (e.clientY - rect.top - rect.height/2 - transform.y) / transform.scale;
                    nodeDragStart = {{ x: mx, y: my }};

                    tooltip.style.display = 'none';
                    render();
                }});

                // Double-click to chain-react: expand node and outputs up to 2 levels
                node.addEventListener('dblclick', (e) => {{
                    e.stopPropagation();
                    const id = node.dataset.id;
                    const label = node.dataset.label;
                    const nodeClass = node.dataset.class;
                    const isFrontierNode = node.dataset.frontier === 'true';

                    // Only allow drilling into entity nodes (not sources)
                    if (nodeClass === 'source') {{
                        log('Cannot expand source nodes', 'info');
                        return;
                    }}

                    // For frontier nodes without routing data, log exploration info
                    const numId = parseInt(id);
                    const hasRoutingData = !isNaN(numId) && routingData[numId];

                    if (!hasRoutingData) {{
                        // For investigation nodes - ADD NEW POTENTIAL NODES based on type
                        const nodeObj = nodes.find(n => String(n.id) === String(id));
                        const displayLabel = nodeObj ? (nodeObj.displayLabel || nodeObj.label) : label;

                        log('EXPANDING: ' + displayLabel, 'action');

                        // Define what can be discovered from each node type
                        const expansionMap = {{
                            'person': [
                                {{type: 'entity', label: 'Email', prefix: 'email_'}},
                                {{type: 'entity', label: 'Phone', prefix: 'phone_'}},
                                {{type: 'entity', label: 'Username', prefix: 'user_'}},
                                {{type: 'address', label: 'Address', prefix: 'addr_'}},
                                {{type: 'company', label: 'Employer', prefix: 'company_'}},
                                {{type: 'domain', label: 'Social Profile', prefix: 'social_'}}
                            ],
                            'company': [
                                {{type: 'person', label: 'Officer', prefix: 'person_'}},
                                {{type: 'person', label: 'Shareholder', prefix: 'person_'}},
                                {{type: 'address', label: 'Reg Address', prefix: 'addr_'}},
                                {{type: 'entity', label: 'Tax ID', prefix: 'taxid_'}},
                                {{type: 'domain', label: 'Website', prefix: 'domain_'}}
                            ],
                            'entity': [
                                {{type: 'person', label: 'Owner', prefix: 'person_'}},
                                {{type: 'domain', label: 'Domain', prefix: 'domain_'}},
                                {{type: 'entity', label: 'Related Email', prefix: 'email_'}},
                                {{type: 'entity', label: 'Password', prefix: 'pass_'}}
                            ],
                            'domain': [
                                {{type: 'person', label: 'Registrant', prefix: 'person_'}},
                                {{type: 'company', label: 'Owner Org', prefix: 'company_'}},
                                {{type: 'address', label: 'WHOIS Address', prefix: 'addr_'}},
                                {{type: 'entity', label: 'Email', prefix: 'email_'}},
                                {{type: 'entity', label: 'IP Address', prefix: 'ip_'}}
                            ],
                            'address': [
                                {{type: 'person', label: 'Resident', prefix: 'person_'}},
                                {{type: 'company', label: 'Business', prefix: 'company_'}},
                                {{type: 'entity', label: 'Phone', prefix: 'phone_'}}
                            ]
                        }};

                        const expansions = expansionMap[nodeClass] || [];
                        if (expansions.length === 0) {{
                            log('No expansion available for ' + nodeClass, 'info');
                            return;
                        }}

                        // Add new placeholder nodes
                        const existingIds = new Set(nodes.map(n => String(n.id)));
                        let addedCount = 0;

                        expansions.forEach((exp, i) => {{
                            const newId = id + '_exp_' + i;
                            if (!existingIds.has(newId)) {{
                                const classification = classifyNode(exp.label, 'entity');
                                nodes.push({{
                                    id: newId,
                                    label: exp.prefix + '???',
                                    displayLabel: exp.label + ' (to discover)',
                                    type: 'entity',
                                    nodeClass: exp.type === 'person' ? 'person' : (exp.type === 'company' ? 'company' : (exp.type === 'address' ? 'address' : (exp.type === 'domain' ? 'domain' : 'entity'))),
                                    shape: exp.type === 'person' ? 'circle' : (exp.type === 'address' ? 'triangle' : 'rect'),
                                    sizeMultiplier: exp.type === 'person' || exp.type === 'company' ? 1.5 : 1.0,
                                    frontier: true
                                }});
                                edges.push({{from: id, to: newId, type: 'potential'}});
                                existingIds.add(newId);
                                addedCount++;
                            }}
                        }});

                        // Mark clicked node as explored
                        if (nodeObj) nodeObj.frontier = false;

                        log('Added ' + addedCount + ' potential nodes', 'success');

                        // Update frontier count
                        const remaining = nodes.filter(n => n.frontier === true).length;
                        if (frontierCount) frontierCount.textContent = remaining;

                        // Recompute layout and render
                        computeLayout();
                        render();
                        setTimeout(fitAll, 100);
                        return;
                    }}

                    log('Expanding: ' + label, 'action');
                    const sources = routingData[numId];
                    let addedNodes = 0;
                    let addedEdges = 0;

                    // Add sources and their outputs (chain reaction up to 2 levels)
                    const existingNodeIds = new Set(nodes.map(n => String(n.id)));
                    const existingEdgeKeys = new Set(edges.map(e => e.from + '-' + e.to));

                    Object.entries(sources).slice(0, 5).forEach(([sourceName, outputs]) => {{
                        const sourceId = 'src_' + Math.abs(sourceName.split('').reduce((a,b) => ((a << 5) - a) + b.charCodeAt(0), 0) & 0xFFFFFFFF);

                        // Add source node if not exists
                        if (!existingNodeIds.has(sourceId)) {{
                            nodes.push({{
                                id: sourceId,
                                label: sourceName,
                                displayLabel: sourceName,
                                type: 'source',
                                nodeClass: 'source',
                                shape: 'rect',
                                sizeMultiplier: 1
                            }});
                            existingNodeIds.add(sourceId);
                            addedNodes++;
                        }}

                        // Add edge from clicked node to source
                        const edgeKey1 = numId + '-' + sourceId;
                        if (!existingEdgeKeys.has(edgeKey1)) {{
                            edges.push({{ from: numId, to: sourceId, type: 'input' }});
                            existingEdgeKeys.add(edgeKey1);
                            addedEdges++;
                        }}

                        // Add output nodes and edges
                        outputs.slice(0, 8).forEach(outCode => {{
                            const outLabel = legend[String(outCode)] || 'field_' + outCode;
                            if (!existingNodeIds.has(String(outCode))) {{
                                const classification = classifyNode(outLabel, 'entity');
                                nodes.push({{
                                    id: outCode,
                                    label: outLabel,
                                    displayLabel: outLabel,
                                    type: 'entity',
                                    nodeClass: classification.class,
                                    shape: classification.shape,
                                    sizeMultiplier: classification.size,
                                    frontier: routingData[outCode] ? true : false
                                }});
                                existingNodeIds.add(String(outCode));
                                addedNodes++;
                            }}

                            const edgeKey2 = sourceId + '-' + outCode;
                            if (!existingEdgeKeys.has(edgeKey2)) {{
                                edges.push({{ from: sourceId, to: outCode, type: 'output' }});
                                existingEdgeKeys.add(edgeKey2);
                                addedEdges++;
                            }}
                        }});
                    }});

                    // Mark clicked node as explored
                    const nodeObj = nodes.find(n => String(n.id) === String(numId));
                    if (nodeObj) nodeObj.frontier = false;

                    log('Added ' + addedNodes + ' nodes, ' + addedEdges + ' edges', 'success');

                    // Update frontier count
                    const remaining = nodes.filter(n => n.frontier === true).length;
                    if (frontierCount) frontierCount.textContent = remaining;

                    // Recompute layout and render
                    computeLayout();
                    render();
                    setTimeout(fitAll, 100);
                }});
            }});
        }}

        // Global mouse move for node dragging - throttled for performance
        let lastDragRender = 0;
        const DRAG_THROTTLE = 16; // ~60fps max

        window.addEventListener('mousemove', (e) => {{
            if (isDraggingNode && selectedNodeId) {{
                const now = Date.now();
                if (now - lastDragRender < DRAG_THROTTLE) return;
                lastDragRender = now;

                const rect = svg.getBoundingClientRect();
                const mx = (e.clientX - rect.left - rect.width/2 - transform.x) / transform.scale;
                const my = (e.clientY - rect.top - rect.height/2 - transform.y) / transform.scale;

                const dx = mx - nodeDragStart.x;
                const dy = my - nodeDragStart.y;

                // Check if we should enter group drag mode (held for 1+ second)
                if (!groupDragMode && (now - nodeDragStartTime) >= GROUP_DRAG_DELAY) {{
                    groupDragMode = true;
                    svg.style.cursor = 'move';
                }}

                if (groupDragMode) {{
                    // Move selected node and all connected nodes
                    const connectedNodes = getConnectedNodes(selectedNodeId);
                    connectedNodes.add(selectedNodeId);
                    connectedNodes.forEach(nodeId => {{
                        if (nodePositions[nodeId]) {{
                            nodePositions[nodeId].x += dx;
                            nodePositions[nodeId].y += dy;
                        }}
                    }});
                }} else {{
                    // Move only the selected node
                    if (nodePositions[selectedNodeId]) {{
                        nodePositions[selectedNodeId].x += dx;
                        nodePositions[selectedNodeId].y += dy;
                    }}
                }}

                nodeDragStart = {{ x: mx, y: my }};
                updatePositions(); // Lightweight update during drag
            }}
        }});

        // Global mouse up to end node dragging
        window.addEventListener('mouseup', (e) => {{
            if (isDraggingNode) {{
                isDraggingNode = false;
                groupDragMode = false;
                svg.style.cursor = 'default';
                render(); // Full render on release to update highlights
            }}
        }});

        // Click on canvas background to deselect
        svg.addEventListener('click', (e) => {{
            if (e.target === svg || e.target.tagName === 'line') {{
                selectedNodeId = null;
                render();
            }}
        }});

        function fitAll() {{
            if (nodes.length === 0) return;

            const positions = Object.values(nodePositions);
            if (positions.length === 0) return;

            const minX = Math.min(...positions.map(p => p.x)) - BASE_NODE_WIDTH * 2;
            const maxX = Math.max(...positions.map(p => p.x)) + BASE_NODE_WIDTH * 2;
            const minY = Math.min(...positions.map(p => p.y)) - BASE_NODE_HEIGHT * 2;
            const maxY = Math.max(...positions.map(p => p.y)) + BASE_NODE_HEIGHT * 2;

            const graphWidth = maxX - minX || 1;
            const graphHeight = maxY - minY || 1;
            const svgWidth = svg.clientWidth - 300;
            const svgHeight = svg.clientHeight - 100;

            // Calculate scale, ensure minimum of 0.3 so it doesn't zoom out too far
            const scale = Math.max(0.3, Math.min(svgWidth / graphWidth, svgHeight / graphHeight, 2));
            const centerX = (minX + maxX) / 2;
            const centerY = (minY + maxY) / 2;

            transform.scale = scale * 0.85;
            transform.x = -centerX * transform.scale;
            transform.y = -centerY * transform.scale;

            render();
        }}

        function reset() {{
            transform = {{ x: 0, y: 0, scale: 1 }};
            spacingMultiplier = 1;
            spacingSlider.value = 100;
            spacingValue.textContent = '100%';
            expandedNodes.clear();
            computeLayout();
            render();
        }}

        // Pan handlers (only when not dragging a node) - NO re-render, just transform update
        svg.addEventListener('mousedown', (e) => {{
            if ((e.target === svg || e.target.tagName === 'line') && !isDraggingNode) {{
                isDragging = true;
                dragStart = {{ x: e.clientX - transform.x, y: e.clientY - transform.y }};
                svg.style.cursor = 'grabbing';
            }}
        }});

        window.addEventListener('mousemove', (e) => {{
            if (isDragging && !isDraggingNode) {{
                transform.x = e.clientX - dragStart.x;
                transform.y = e.clientY - dragStart.y;
                // Just update the transform attribute, don't rebuild
                const mainGroup = svg.querySelector('g');
                if (mainGroup) {{
                    const width = svg.clientWidth;
                    const height = svg.clientHeight;
                    mainGroup.setAttribute('transform', 'translate(' + (width/2 + transform.x) + ',' + (height/2 + transform.y) + ') scale(' + transform.scale + ')');
                }}
            }}
        }});

        window.addEventListener('mouseup', () => {{
            if (isDragging) {{
                isDragging = false;
                svg.style.cursor = 'default';
            }}
        }});

        // Zoom handler - wider range for large graphs, NO re-render
        svg.addEventListener('wheel', (e) => {{
            e.preventDefault();
            const delta = e.deltaY > 0 ? 0.85 : 1.18;
            const newScale = Math.max(0.05, Math.min(10, transform.scale * delta));

            // Zoom toward mouse position
            const rect = svg.getBoundingClientRect();
            const mx = e.clientX - rect.left - rect.width / 2;
            const my = e.clientY - rect.top - rect.height / 2;

            transform.x = mx - (mx - transform.x) * (newScale / transform.scale);
            transform.y = my - (my - transform.y) * (newScale / transform.scale);
            transform.scale = newScale;

            // Just update transform, don't rebuild
            const mainGroup = svg.querySelector('g');
            if (mainGroup) {{
                const width = svg.clientWidth;
                const height = svg.clientHeight;
                mainGroup.setAttribute('transform', 'translate(' + (width/2 + transform.x) + ',' + (height/2 + transform.y) + ') scale(' + transform.scale + ')');
            }}
        }});

        // Spacing slider
        spacingSlider.addEventListener('input', () => {{
            spacingMultiplier = spacingSlider.value / 100;
            spacingValue.textContent = spacingSlider.value + '%';
            computeLayout();
            render();
        }});

        // Buttons
        fitBtn.addEventListener('click', fitAll);
        resetBtn.addEventListener('click', reset);

        // Frontier toggle button - shows unexplored nodes grouped by type
        frontierBtn.addEventListener('click', () => {{
            showFrontier = !showFrontier;
            frontierBtn.textContent = showFrontier ? 'Hide Unexplored' : 'Show Unexplored';
            frontierBtn.style.background = showFrontier ? '#ec4899' : '#1e293b';
            frontierInfo.style.display = showFrontier ? 'block' : 'none';

            if (showFrontier) {{
                // Group unexplored nodes by type and log them
                const unexploredByType = {{}};
                nodes.forEach(n => {{
                    if (n.frontier === true) {{
                        const nodeClass = n.nodeClass || 'entity';
                        if (!unexploredByType[nodeClass]) unexploredByType[nodeClass] = [];
                        unexploredByType[nodeClass].push(n.displayLabel || n.label);
                    }}
                }});

                // Log each type
                Object.entries(unexploredByType).forEach(([type, labels]) => {{
                    log(type.toUpperCase() + ' (' + labels.length + '): ' + labels.slice(0,3).join(', ') + (labels.length > 3 ? '...' : ''), 'action');
                }});

                if (Object.keys(unexploredByType).length === 0) {{
                    log('No unexplored nodes found', 'info');
                }} else {{
                    log('Double-click a magenta node to explore', 'info');
                }}
            }}

            render();
        }});

        // Filter handlers
        Object.entries(filters).forEach(([filterClass, checkbox]) => {{
            if (checkbox) {{
                checkbox.addEventListener('change', () => {{
                    if (checkbox.checked) {{
                        hiddenClasses.delete(filterClass);
                        log('Showing ' + filterClass + ' nodes', 'info');
                    }} else {{
                        hiddenClasses.add(filterClass);
                        // Count how many nodes will be hidden
                        const hideCount = nodes.filter(n => (n.nodeClass || 'entity') === filterClass).length;
                        log('Hiding ' + hideCount + ' ' + filterClass + ' nodes', 'action');
                    }}
                    render();
                }});
            }}
        }});

        // Run IO on Type buttons - opens io_cli for unexplored nodes of that type
        document.querySelectorAll('.run-type-btn').forEach(btn => {{
            btn.addEventListener('click', () => {{
                const targetType = btn.dataset.type;

                // Find unexplored (frontier) nodes of this type
                const unexploredOfType = nodes.filter(n =>
                    n.frontier === true && (n.nodeClass || 'entity') === targetType
                );

                if (unexploredOfType.length === 0) {{
                    log('No unexplored ' + targetType + ' nodes', 'info');
                    return;
                }}

                log('Running IO on ' + unexploredOfType.length + ' ' + targetType + ' nodes...', 'action');

                // Map node class to IO Matrix field type
                const typeToField = {{
                    'person': 'person_name',
                    'company': 'company_name',
                    'entity': 'email',
                    'domain': 'domain_url',
                    'address': 'address'
                }};
                const ioField = typeToField[targetType] || targetType;

                // Open IO visualization for this field type
                const ioUrl = 'http://localhost:3000/io?field=' + encodeURIComponent(ioField);

                // Log each node being processed
                unexploredOfType.forEach(n => {{
                    log('  → ' + (n.displayLabel || n.label), 'info');
                    // Mark as explored
                    n.frontier = false;
                }});

                // Update frontier count
                const remaining = nodes.filter(n => n.frontier === true).length;
                if (frontierCount) frontierCount.textContent = remaining;

                // Open new tab with IO Matrix for this field type
                window.open('data:text/html,<html><head><title>IO Matrix: ' + ioField + '</title></head><body style=\"background:%230f172a;color:white;font-family:Inter,sans-serif;padding:40px;\"><h1>IO Matrix: ' + ioField + '</h1><p>Run in terminal:</p><pre style=\"background:%231e293b;padding:20px;border-radius:8px;\">python3 input_output2/matrix/io_cli.py --viz ' + ioField + ' --depth 2</pre><h2>Unexplored ' + targetType + ' nodes:</h2><ul>' + unexploredOfType.map(n => '<li>' + (n.displayLabel || n.label) + '</li>').join('') + '</ul></body></html>', '_blank');

                render();
            }});
        }});

        // Initial render
        computeLayout();
        render();
        setTimeout(fitAll, 100);
    }})();
    </script>
</body>
</html>'''
    return html


# =============================================================================
# ALEPH ENRICHMENT - Add OCCRP Aleph results to country searches
# =============================================================================

def enrich_with_aleph(result_dict: Dict, query_value: str, jurisdiction: str, entity_type: str = 'company', section: str = None) -> Dict:
    """
    Enrich country search results with OCCRP Aleph data.

    Called by country operator handlers (cuk:, cbe:, chr:, etc.) to add
    Aleph collection results alongside native registry data.

    Args:
        result_dict: Existing result dictionary from country CLI
        query_value: The search query (company name, person name, etc.)
        jurisdiction: ISO country code (GB, BE, HR, etc.)
        entity_type: 'company' or 'person'
        section: Wiki section filter (cr, lit, reg, ass, leak, news) - None for all

    Returns:
        Enriched result_dict with 'aleph' key added

    Section mapping:
        cr   = Corporate Registry (company, gazette)
        lit  = Litigation (court)
        reg  = Regulatory (regulatory, sanctions, license, procurement, poi)
        ass  = Assets (land, finance, transport)
        leak = Leaks & Grey Literature (leak, grey, library)
        news = News & Media (news)
    """
    import asyncio

    try:
        # Load Aleph collections
        collections_path = MATRIX_DIR / "aleph_collections.json"
        if not collections_path.exists():
            return result_dict

        with open(collections_path) as f:
            aleph_collections = json.load(f)

        # Get section mapping for category filtering
        section_mapping = aleph_collections.get('meta', {}).get('section_mapping', {})
        allowed_categories = None
        if section and section in section_mapping:
            allowed_categories = set(section_mapping[section].get('categories', []))

        # Check if this jurisdiction has Aleph collections
        jurisdiction_upper = jurisdiction.upper()
        jurisdiction_data = aleph_collections.get('by_jurisdiction', {}).get(jurisdiction_upper, {})

        # Filter collections by section if specified
        if jurisdiction_data and allowed_categories:
            filtered_collections = [
                c for c in jurisdiction_data.get('collections', [])
                if c.get('category') in allowed_categories
            ]
            if not filtered_collections:
                # No collections match this section for this jurisdiction
                return result_dict

        # Load AlephSearcher from unified corporella module
        sys.path.insert(0, str(BACKEND_PATH / "corporella"))
        from occrp_aleph import AlephSearcher

        # Map entity type to schemas
        schema_map = {
            'company': ['Company', 'LegalEntity'],
            'person': ['Person'],
        }
        schemas = schema_map.get(entity_type, ['Company', 'LegalEntity'])

        # Search Aleph
        async def do_search():
            searcher = AlephSearcher()
            return await searcher.search(query_value, max_results=30, schemas=schemas)

        aleph_results = asyncio.run(do_search())

        # Filter results by category if section specified
        if aleph_results and allowed_categories:
            # Note: Aleph results don't have category directly, but we searched with section filter intent
            # The category filtering is more for local collection routing than result filtering
            pass

        # Add to result_dict
        if aleph_results:
            section_label = section_mapping.get(section, {}).get('name', 'All') if section else 'All'
            if 'aleph' not in result_dict:
                result_dict['aleph'] = {
                    'status': 'ok',
                    'jurisdiction': jurisdiction_upper,
                    'query': query_value,
                    'section': section,
                    'section_name': section_label,
                    'results_count': len(aleph_results),
                    'results': aleph_results
                }
            else:
                # Merge with existing
                result_dict['aleph']['results'].extend(aleph_results)
                result_dict['aleph']['results_count'] = len(result_dict['aleph']['results'])

        # Also add to modules_run if it exists
        if 'modules_run' in result_dict:
            module_name = f'OCCRP-Aleph-{section.upper()}' if section else 'OCCRP-Aleph'
            if module_name not in result_dict['modules_run']:
                result_dict['modules_run'].append(module_name)

    except ImportError as e:
        logger.debug(f"Aleph module not available for enrichment: {e}")
    except Exception as e:
        logger.warning(f"Aleph enrichment failed: {e}")
        if 'errors' in result_dict:
            result_dict['errors'].append(f"Aleph enrichment: {str(e)}")

    return result_dict


def main():
    parser = argparse.ArgumentParser(
        description="IO CLI - The Single Entry Point for Investigation Operations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EXECUTION MODE (prefix operators + LINKLATER operators):
  %(prog)s "p: John Smith"                        # Full person investigation
  %(prog)s "c: Acme Corp" --jurisdiction US       # Company investigation (US)
  %(prog)s "e: john@acme.com"                     # Email investigation
  %(prog)s "t: +1-555-1234"                       # Phone investigation
  %(prog)s "li: melissa-smet-529476130"           # LinkedIn slug → linkedin_url
  %(prog)s "d: acme.com"                          # Domain investigation
  %(prog)s "social: John Smith"                   # Social search links (BRUTE)
  %(prog)s "p: John Smith" --dry-run              # Show plan without executing
  %(prog)s "p: John Smith" --results-viz          # Investigation + results graph
  %(prog)s "?bl:!acme.com"                        # Linklater backlinks (domains)
  %(prog)s "bl?:!acme.com"                        # Linklater backlinks (pages)
  %(prog)s "ent?:2024! !acme.com"                 # Linklater historical entities
  %(prog)s "pdf!:!acme.com"                       # Linklater file discovery
  %(prog)s "\"keyword\" :tor"                     # Linklater Tor search

ROUTING MODE (lookup capabilities):
  %(prog)s --have email                           # What can I get from an email?
  %(prog)s --have email --want company_officers   # How to get officers from email?
  %(prog)s --graph domain --depth 2               # Graph data centered on domain
  %(prog)s --viz email --depth 2                  # Source capability graph (opt-in)
  %(prog)s --stats                                # Matrix statistics
  %(prog)s --legend company                       # Search field names

Prefixes:
  p: = person    c: = company    e: = email    t: = phone    d: = domain    u: = username    li: = linkedin_url    liu: = linkedin_username
        """
    )

    # EXECUTION arguments (new)
    parser.add_argument(
        "query",
        nargs="?",
        help="Query with prefix (p:, c:, e:, t:, d:, u:, li:, liu:, social:) or LINKLATER operator syntax"
    )
    parser.add_argument("-j", "--jurisdiction", help="Filter by jurisdiction (US, UK, DE, etc.)")
    parser.add_argument("--dry-run", action="store_true", help="Show execution plan without running")

    # ROUTING arguments (existing)
    parser.add_argument("--have", help="Input field you have")
    parser.add_argument("--want", help="Output field you want")
    parser.add_argument("--show-capabilities", action="store_true", help="Show what outputs are possible")
    parser.add_argument("--find-path", action="store_true", help="Find path from input to output")
    parser.add_argument("--graph", help="Get graph data centered on a field")
    parser.add_argument("--viz", help="Generate source capability visualization for a field (opt-in)")
    parser.add_argument("--depth", type=int, default=2, help="Graph exploration depth (default: 2)")
    parser.add_argument("--stats", action="store_true", help="Show matrix statistics")
    parser.add_argument("--legend", help="Search legend for fields matching query")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--results-viz", action="store_true", help="Show interactive visualization of investigation results")
    parser.add_argument("--with-graph", action="store_true", help="Include graph nodes/edges from country registry results")
    parser.add_argument("--project", type=str, help="Project ID for Elasticsearch persistence (cymonides-1-{project}). Required with --with-graph for persistence.")
    parser.add_argument("--recurse", action="store_true", help="Recursively pivot discovered entities back into IO execution")
    parser.add_argument("--max-depth", type=int, default=2, help="Max recursion depth for --recurse (default: 2)")
    parser.add_argument("--max-nodes", type=int, default=50, help="Max total nodes executed for --recurse (default: 50)")
    parser.add_argument(
        "--recurse-types",
        type=str,
        default="email,phone,domain,linkedin_url,username",
        help="Comma-separated entity types to recurse into (default: email,phone,domain,linkedin_url,username)",
    )

    # MODULE INFO arguments (new)
    parser.add_argument("--list-modules", action="store_true", help="List available execution modules")
    parser.add_argument("--module-info", help="Show info about a specific module")

    # MACRO arguments
    parser.add_argument("--macro-logs", action="store_true", help="Show recent macro execution logs")
    parser.add_argument("--list-macros", action="store_true", help="List available macros")
    parser.add_argument("--domain", help="Domain for macros that require it (e.g., crel?)")
    parser.add_argument("--address", help="Address for macros that require it")

    args = parser.parse_args()

    router = IORouter()

    def output(data):
        if args.json:
            print(json.dumps(data, indent=2))
        else:
            if isinstance(data, dict):
                if "error" in data:
                    print(f"Error: {data['error']}")
                    return
                for key, value in data.items():
                    if isinstance(value, list):
                        print(f"\n{key}:")
                        for item in value[:20]:
                            if isinstance(item, dict):
                                print(f"  - {item}")
                            else:
                                print(f"  - {item}")
                        if len(value) > 20:
                            print(f"  ... and {len(value) - 20} more")
                    else:
                        print(f"{key}: {value}")
            else:
                print(data)

    # Source capability visualization - NOW OPT-IN with --viz flag only
    # (Previously was auto-on which was confusing - user wants RESULT viz, not source viz)
    def visualize_sources(center_field: str):
        """Visualize source capabilities (what fields can produce what outputs)."""
        if center_field:
            graph_data = router.get_graph_data(center_field, args.depth)
            if "error" not in graph_data:
                html = generate_viz_html(graph_data, router)
                with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
                    f.write(html)
                    print(f"\n📊 Source Capability Graph: {f.name}")
                    webbrowser.open(f'file://{f.name}')

    # =========================================================================
    # MACRO LOGS MODE - Show recent macro execution logs
    # =========================================================================
    if args.macro_logs:
        logs = MacroLogger.get_recent_logs(limit=50)
        if not logs:
            print("No macro execution logs found.")
            return

        print(f"\n{'='*60}")
        print("RECENT MACRO EXECUTIONS")
        print(f"{'='*60}\n")

        for log in reversed(logs):
            status = "✓" if log.get('success') else "✗"
            print(f"{status} [{log.get('timestamp', '')}] {log.get('macro_name', '')}:")
            print(f"   Input: {log.get('input_value', '')[:50]}...")
            print(f"   Duration: {log.get('duration_seconds', 0):.2f}s")
            print(f"   Outputs: {log.get('output_count', 0)} items")
            if log.get('error'):
                print(f"   Error: {log.get('error')[:80]}")
            print()

        if args.json:
            print(json.dumps(logs, indent=2))
        return

    # =========================================================================
    # LIST MACROS MODE - Show available macros
    # =========================================================================
    if args.list_macros:
        macro_executor = MacroExecutor()
        print(f"\n{'='*60}")
        print("AVAILABLE MACROS")
        print(f"{'='*60}\n")

        for macro_name in sorted(macro_executor.available_macros):
            io_codes = MacroLogger.MACRO_IO_CODES.get(macro_name, {})
            print(f"  {macro_name}:")
            print(f"    Input code: {io_codes.get('input', 'N/A')}")
            print(f"    Output codes: {io_codes.get('outputs', [])}")

            # Find the operator for this macro
            for op, name in MacroExecutor.MACRO_OPERATORS.items():
                if name == macro_name:
                    print(f"    Operator: {op}?")
                    break
            print()

        if args.json:
            output({'macros': macro_executor.available_macros})
        return

    # =========================================================================
    # MACRO OPERATOR MODE - Handle macro operators (cdom?, alldom?, crel?, etc.)
    # =========================================================================
    if args.query:
        macro_executor = MacroExecutor(dry_run=args.dry_run)
        macro_parsed = macro_executor.parse_macro_operator(args.query)
        if macro_parsed:
            macro_name, value = macro_parsed
            if not args.json:
                print(f"\n{'='*60}")
                print(f"MACRO: {macro_name.upper()}")
                print(f"{'='*60}")
                print(f"Input: {value}")
                if args.dry_run:
                    print("Mode: DRY RUN")
                print(f"{'='*60}\n")

            result = asyncio.run(macro_executor.execute(
                macro_name,
                value,
                jurisdiction=args.jurisdiction,
                domain=args.domain,
                address=args.address,
            ))
            output(result)

            if args.results_viz and not args.dry_run:
                # Convert macro result to viz format
                viz_result = {
                    'entity_type': macro_name,
                    'value': value,
                    'results': result,
                }
                html = generate_results_viz_html(viz_result)
                with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
                    f.write(html)
                    print(f"\n📊 Results Visualization: {f.name}")
                    webbrowser.open(f'file://{f.name}')
            return

    # =========================================================================
    # LINKLATER OPERATOR MODE - Handle LINKLATER operator syntax
    # =========================================================================
    linklater_parsed = _try_parse_linklater(args.query) if args.query else None
    if args.query and _looks_like_linklater_query(args.query, linklater_parsed):
        if not args.json:
            print(f"\n{'='*60}")
            print("LINKLATER OPERATOR")
            print(f"{'='*60}")
            print(f"Query: {args.query}")
            if args.dry_run:
                print("Mode: DRY RUN (parsed only)")
            print(f"{'='*60}\n")

        result = _run_linklater_query(args.query, parsed=linklater_parsed, dry_run=args.dry_run)
        output(result)

        if args.results_viz and not args.dry_run:
            viz_result = _linklater_results_for_viz(args.query, result, parsed=linklater_parsed)
            html = generate_results_viz_html(viz_result)
            with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
                f.write(html)
                print(f"\n📊 Results Visualization: {f.name}")
                webbrowser.open(f'file://{f.name}')
        return

    # =========================================================================
    # MATRIX EXPLORATION MODE - Handle [?]=>TYPE, TYPE=>[?] queries
    # =========================================================================
    if args.query and '=>' in args.query:
        # Check if this is "prefix:value =>[?]" pattern (e.g., "chr:xyz doo =>[?]")
        # In this case, strip the =>[?] and treat as normal execution
        execution_with_hint = re.match(r'^([a-z]{1,6}:\s*.+?)\s*=>\s*\[?\?\]?\s*$', args.query, re.IGNORECASE)
        if execution_with_hint:
            # Strip the =>[?] suffix - treat as normal execution
            args.query = execution_with_hint.group(1).strip()
            # Fall through to EXECUTION MODE below
        else:
            matrix_query = parse_matrix_query(args.query)
            if matrix_query:
                explorer = MatrixExplorer()
                result = explorer.explore(matrix_query)

                print(f"\n{'='*60}")
                print(f"MATRIX EXPLORATION: {result.get('question', matrix_query['mode'].upper())}")
                print(f"{'='*60}")

                if args.json:
                    output(result)
                else:
                    # Pretty print results based on mode
                    if matrix_query['mode'] == 'forward':
                        print(f"\nInput: {result.get('input_type')} (code: {result.get('input_code')})")
                        if result.get('jurisdiction'):
                            print(f"Jurisdiction: {result['jurisdiction']}")

                        if result.get('outputs'):
                            print(f"\n📤 AVAILABLE OUTPUTS ({len(result['outputs'])} routes):")
                            for out in result['outputs']:
                                jur = f" [{out['jurisdiction']}]" if out.get('jurisdiction') else ""
                                print(f"  → {out['output_type']}{jur}")
                                print(f"    Source: {out.get('source', 'unknown')}")
                                if out.get('description'):
                                    print(f"    Note: {out['description']}")

                        if result.get('sources'):
                            print(f"\n🔌 EXECUTION SOURCES ({len(result['sources'])}):")
                            for src in result['sources']:
                                if src['type'] == 'module':
                                    jur_req = " ⚠️ requires jurisdiction" if src.get('requires_jurisdiction') else ""
                                    print(f"  [MODULE] {src['module']}.{src['method']}{jur_req}")
                                else:
                                    print(f"  [ES] {src['index']} ({src.get('cluster', 'unknown')})")

                    elif matrix_query['mode'] == 'reverse':
                        print(f"\nOutput sought: {result.get('output_type')} (code: {result.get('output_code')})")
                        if result.get('jurisdiction_filter'):
                            print(f"Jurisdiction filter: {result['jurisdiction_filter']}")

                        if result.get('routes'):
                            print(f"\n📥 INPUT ROUTES ({len(result['routes'])} found):")
                            for route in result['routes']:
                                jur = f" [{route['jurisdiction']}]" if route.get('jurisdiction') else ""
                                print(f"  ← {route['input_type']}{jur}")
                                print(f"    Source: {route.get('source', 'unknown')}")
                                if route.get('description'):
                                    print(f"    Note: {route['description']}")

                        if result.get('sources'):
                            print(f"\n🔌 DATA SOURCES ({len(result['sources'])}):")
                            for src in result['sources']:
                                if src['type'] == 'module':
                                    print(f"  [MODULE] {src['module']}.{src['method']} (input: {src.get('input_type')})")
                                else:
                                    print(f"  [ES] {src['index']} ({src.get('cluster', 'unknown')})")

                    elif matrix_query['mode'] == 'route':
                        print(f"\nRoute: {result.get('input_type')} → {result.get('output_type')}")

                        if result.get('direct_routes'):
                            print(f"\n✅ DIRECT ROUTES ({len(result['direct_routes'])}):")
                            for route in result['direct_routes']:
                                jur = f" [{route['jurisdiction']}]" if route.get('jurisdiction') else ""
                                print(f"  {route.get('source', 'unknown')}{jur}")
                                if route.get('description'):
                                    print(f"    {route['description']}")

                        if result.get('chain_routes'):
                            print(f"\n🔗 CHAIN ROUTES ({len(result['chain_routes'])} found):")
                            for chain in result['chain_routes']:
                                print(f"  via {chain['via']}:")
                                print(f"    Step 1: {chain['step1'].get('source')} - {chain['step1'].get('description', '')}")
                                print(f"    Step 2: {chain['step2'].get('source')} - {chain['step2'].get('description', '')}")

                    if not result.get('direct_routes') and not result.get('chain_routes'):
                        print("\n❌ No routes found between these types")

                print(f"\n{'='*60}")
                sys.exit(0)

    # =========================================================================
    # COUNTRY GRAPH ADAPTER - Convert country CLI results to nodes/edges
    # =========================================================================
    def add_graph_output(result_dict: dict, result_obj, jurisdiction: str) -> dict:
        """
        Add graph nodes/edges to result if --with-graph is specified.

        MANDATORY: If --project is provided, persists to cymonides-1-{project}.
        The IO system is ALWAYS part of drill-search-app with a live project.
        """
        if not args.with_graph:
            return result_dict
        try:
            from country_graph_adapter import CountryGraphAdapter

            project_id = getattr(args, 'project', None)
            adapter = CountryGraphAdapter(project_id=project_id)
            graph_result = adapter.from_result(result_obj, jurisdiction)
            result_dict['graph'] = graph_result.to_dict()

            if not args.json:
                print(f"\n--- GRAPH OUTPUT ---")
                print(f"Nodes: {len(graph_result.nodes)}")
                for node in graph_result.nodes[:5]:
                    print(f"  [{node.node_type}] {node.label}")
                if len(graph_result.nodes) > 5:
                    print(f"  ... and {len(graph_result.nodes) - 5} more")
                print(f"Edges: {len(graph_result.edges)}")
                for edge in graph_result.edges[:5]:
                    print(f"  {edge.edge_type}")
                if len(graph_result.edges) > 5:
                    print(f"  ... and {len(graph_result.edges) - 5} more")

            # PERSIST TO ELASTICSEARCH if project_id is provided
            if project_id:
                if not args.json:
                    print(f"\n--- ELASTICSEARCH PERSISTENCE ---")
                    print(f"Target index: cymonides-1-{project_id}")

                try:
                    stats = asyncio.run(adapter.persist_to_elastic(graph_result, project_id))
                    result_dict['persistence'] = stats

                    if not args.json:
                        print(f"  ✓ Nodes created: {stats.get('nodes_created', 0)}")
                        print(f"  ✓ Nodes updated: {stats.get('nodes_updated', 0)}")
                        print(f"  ✓ Edges embedded: {stats.get('edges_embedded', 0)}")
                except Exception as e:
                    error_msg = f"Elasticsearch persistence failed: {e}"
                    logger.error(error_msg)
                    result_dict['persistence_error'] = str(e)
                    if not args.json:
                        print(f"  ✗ {error_msg}")
            else:
                if not args.json:
                    print(f"\n  ⚠ No --project specified. Graph not persisted to Elasticsearch.")
                    print(f"  Use: --with-graph --project <project_id>")

        except ImportError as e:
            logger.warning(f"Graph adapter not available: {e}")
        except Exception as e:
            logger.warning(f"Graph conversion failed: {e}")
        return result_dict

    # =========================================================================
    # UK OPERATOR MODE - Handle UK-specific operators (cuk:, puk:, reguk:, lituk:, etc.)
    # =========================================================================
    if args.query:
        query_lower = args.query.strip().lower()
        uk_operator_prefixes = ['cuk:', 'puk:', 'reguk:', 'lituk:', 'cruk:', 'assuk:', 'foiuk:', 'docuk:']

        if any(query_lower.startswith(prefix) for prefix in uk_operator_prefixes):
            if not args.json:
                print(f"\n{'='*60}")
                print("UK PUBLIC RECORDS SEARCH")
                print(f"{'='*60}")
                print(f"Query: {args.query}")
                if args.dry_run:
                    print("Mode: DRY RUN (parsed only)")
                print(f"{'='*60}\n")

            # Execute via UK Unified CLI
            try:
                from country_engines.UK.uk_unified_cli import UKUnifiedCLI
                uk_cli = UKUnifiedCLI()
                result = asyncio.run(uk_cli.execute(args.query))
                result_dict = result.to_dict() if hasattr(result, 'to_dict') else result
                result_dict = add_graph_output(result_dict, result, "GB")

                # Enrich with OCCRP Aleph (UK collections: Companies House, PSC, etc.)
                query_value = args.query.split(':', 1)[1].strip() if ':' in args.query else args.query
                entity_type = 'person' if query_lower.startswith('puk:') else 'company'
                # Detect section from operator prefix
                section = None
                if query_lower.startswith('reguk:'):
                    section = 'reg'
                elif query_lower.startswith('lituk:'):
                    section = 'lit'
                elif query_lower.startswith('assuk:'):
                    section = 'ass'
                elif query_lower.startswith('cruk:'):
                    section = 'cr'
                # cuk:/puk: = all sections (section=None)
                result_dict = enrich_with_aleph(result_dict, query_value, 'GB', entity_type, section)

                output(result_dict)
            except ImportError as e:
                print(f"Error: UK module not available: {e}")
                print("Falling back to standard IO routing...")
                # Fall through to standard execution
            except Exception as e:
                print(f"Error executing UK query: {e}")
            else:
                sys.exit(0)

    # =========================================================================
    # US STATE OPERATOR MODE - Handle US state operators (cusca:, pusca:, regusca:, etc.)
    # =========================================================================
    if args.query:
        query_lower = args.query.strip().lower()
        us_match = re.match(r'^(us|cus|pus|regus|litus|assus|crus|newsus)([a-z]{2})?:', query_lower)

        if us_match:
            state_code = us_match.group(2)
            display_jurisdiction = f"US-{state_code.upper()}" if state_code else "US"
            if not args.json:
                print(f"\n{'='*60}")
                print("US PUBLIC RECORDS SEARCH")
                print(f"{'='*60}")
                print(f"Query: {args.query}")
                print(f"Jurisdiction: {display_jurisdiction}")
                print(f"{'='*60}\n")

            try:
                from country_engines.US.us_cli import USCLI
                us_cli = USCLI()
                result = asyncio.run(us_cli.execute(args.query))
                result_dict = result.to_dict() if hasattr(result, 'to_dict') else result
                graph_jurisdiction = f"US_{state_code.upper()}" if state_code else "US"
                result_dict = add_graph_output(result_dict, result, graph_jurisdiction)
                output(result_dict)
            except ImportError as e:
                print(f"Error: US module not available: {e}")
            except Exception as e:
                print(f"Error executing US query: {e}")
            else:
                sys.exit(0)

    # =========================================================================
    # NORWAY OPERATOR MODE - Handle Norwegian operators (cno:, pno:)
    # =========================================================================
    if args.query:
        query_lower = args.query.strip().lower()
        no_operator_prefixes = ['cno:', 'pno:']

        if any(query_lower.startswith(prefix) for prefix in no_operator_prefixes):
            if not args.json:
                print(f"\n{'='*60}")
                print("NORWEGIAN PUBLIC RECORDS SEARCH")
                print(f"{'='*60}")
                print(f"Query: {args.query}")
                print(f"{'='*60}\n")

            # Execute via Norway Unified CLI
            try:
                from country_engines.NO.no_unified_cli import NOUnifiedCLI
                no_cli = NOUnifiedCLI()
                result = asyncio.run(no_cli.execute(args.query))
                result_dict = result.to_dict() if hasattr(result, 'to_dict') else result
                result_dict = add_graph_output(result_dict, result, "NO")

                # Enrich with OCCRP Aleph (Norway collections)
                query_value = args.query.split(':', 1)[1].strip() if ':' in args.query else args.query
                entity_type = 'person' if query_lower.startswith('pno:') else 'company'
                result_dict = enrich_with_aleph(result_dict, query_value, 'NO', entity_type)

                output(result_dict)
            except ImportError as e:
                print(f"Error: Norway module not available: {e}")
            except Exception as e:
                print(f"Error executing Norway query: {e}")
            else:
                sys.exit(0)

    # =========================================================================
    # FINLAND OPERATOR MODE - Handle Finnish operators (cfi:)
    # =========================================================================
    if args.query:
        query_lower = args.query.strip().lower()
        fi_operator_prefixes = ['cfi:']

        if any(query_lower.startswith(prefix) for prefix in fi_operator_prefixes):
            if not args.json:
                print(f"\n{'='*60}")
                print("FINNISH PUBLIC RECORDS SEARCH")
                print(f"{'='*60}")
                print(f"Query: {args.query}")
                print(f"{'='*60}\n")

            # Execute via Finland Unified CLI
            try:
                from country_engines.FI.fi_unified_cli import FIUnifiedCLI
                fi_cli = FIUnifiedCLI()
                result = asyncio.run(fi_cli.execute(args.query))
                result_dict = result.to_dict() if hasattr(result, 'to_dict') else result
                result_dict = add_graph_output(result_dict, result, "FI")

                # Enrich with OCCRP Aleph (Finland collections)
                query_value = args.query.split(':', 1)[1].strip() if ':' in args.query else args.query
                result_dict = enrich_with_aleph(result_dict, query_value, 'FI', 'company')

                output(result_dict)
            except ImportError as e:
                print(f"Error: Finland module not available: {e}")
            except Exception as e:
                print(f"Error executing Finland query: {e}")
            else:
                sys.exit(0)

    # =========================================================================
    # SWITZERLAND OPERATOR MODE - Handle Swiss operators (cch:)
    # =========================================================================
    if args.query:
        query_lower = args.query.strip().lower()
        ch_operator_prefixes = ['cch:']

        if any(query_lower.startswith(prefix) for prefix in ch_operator_prefixes):
            if not args.json:
                print(f"\n{'='*60}")
                print("SWISS PUBLIC RECORDS SEARCH")
                print(f"{'='*60}")
                print(f"Query: {args.query}")
                print(f"{'='*60}\n")

            # Execute via Switzerland Unified CLI
            try:
                from country_engines.CH.ch_unified_cli import CHUnifiedCLI
                ch_cli = CHUnifiedCLI()
                result = asyncio.run(ch_cli.execute(args.query))
                result_dict = result.to_dict() if hasattr(result, 'to_dict') else result
                result_dict = add_graph_output(result_dict, result, "CH")

                # Enrich with OCCRP Aleph (Switzerland collections)
                query_value = args.query.split(':', 1)[1].strip() if ':' in args.query else args.query
                result_dict = enrich_with_aleph(result_dict, query_value, 'CH', 'company')

                output(result_dict)
            except ImportError as e:
                print(f"Error: Switzerland module not available: {e}")
            except Exception as e:
                print(f"Error executing Switzerland query: {e}")
            else:
                sys.exit(0)

    # =========================================================================
    # IRELAND OPERATOR MODE - Handle Irish operators (cie:)
    # =========================================================================
    if args.query:
        query_lower = args.query.strip().lower()
        ie_operator_prefixes = ['cie:']

        if any(query_lower.startswith(prefix) for prefix in ie_operator_prefixes):
            if not args.json:
                print(f"\n{'='*60}")
                print("IRISH PUBLIC RECORDS SEARCH")
                print(f"{'='*60}")
                print(f"Query: {args.query}")
                print(f"{'='*60}\n")

            # Execute via Ireland Unified CLI
            try:
                from country_engines.IE.ie_unified_cli import IEUnifiedCLI
                ie_cli = IEUnifiedCLI()
                result = asyncio.run(ie_cli.execute(args.query))
                result_dict = result.to_dict() if hasattr(result, 'to_dict') else result
                result_dict = add_graph_output(result_dict, result, "IE")

                # Enrich with OCCRP Aleph (Ireland collections)
                query_value = args.query.split(':', 1)[1].strip() if ':' in args.query else args.query
                result_dict = enrich_with_aleph(result_dict, query_value, 'IE', 'company')

                output(result_dict)
            except ImportError as e:
                print(f"Error: Ireland module not available: {e}")
            except Exception as e:
                print(f"Error executing Ireland query: {e}")
            else:
                sys.exit(0)

    # =========================================================================
    # CZECH REPUBLIC OPERATOR MODE - Handle Czech operators (ccz:)
    # =========================================================================
    if args.query:
        query_lower = args.query.strip().lower()
        cz_operator_prefixes = ['ccz:']

        if any(query_lower.startswith(prefix) for prefix in cz_operator_prefixes):
            if not args.json:
                print(f"\n{'='*60}")
                print("CZECH REPUBLIC PUBLIC RECORDS SEARCH (ARES)")
                print(f"{'='*60}")
                print(f"Query: {args.query}")
                print(f"{'='*60}\n")

            # Execute via Czech Republic CLI
            try:
                from country_engines.CZ.cz_cli import CZUnifiedCLI
                cz_cli = CZUnifiedCLI()
                result = asyncio.run(cz_cli.execute(args.query))
                result_dict = result.to_dict() if hasattr(result, 'to_dict') else result
                result_dict = add_graph_output(result_dict, result, "CZ")

                # Enrich with OCCRP Aleph (Czech collections)
                query_value = args.query.split(':', 1)[1].strip() if ':' in args.query else args.query
                result_dict = enrich_with_aleph(result_dict, query_value, 'CZ', 'company')

                output(result_dict)
            except ImportError as e:
                print(f"Error: Czech Republic module not available: {e}")
            except Exception as e:
                print(f"Error executing Czech Republic query: {e}")
            else:
                sys.exit(0)

    # =========================================================================
    # BELGIUM OPERATOR MODE - Handle Belgian operators (cbe:)
    # =========================================================================
    if args.query:
        query_lower = args.query.strip().lower()
        be_operator_prefixes = ['cbe:']

        if any(query_lower.startswith(prefix) for prefix in be_operator_prefixes):
            if not args.json:
                print(f"\n{'='*60}")
                print("BELGIUM KBO/BCE PUBLIC RECORDS SEARCH")
                print(f"{'='*60}")
                print(f"Query: {args.query}")
                print(f"{'='*60}\n")

            # Execute via Belgium Unified CLI
            try:
                from country_engines.BE.be_cli import BEUnifiedCLI
                be_cli = BEUnifiedCLI()
                result = asyncio.run(be_cli.execute(args.query))
                result_dict = result.to_dict() if hasattr(result, 'to_dict') else result
                result_dict = add_graph_output(result_dict, result, "BE")

                # Enrich with OCCRP Aleph (Belgium collections)
                query_value = args.query.split(':', 1)[1].strip() if ':' in args.query else args.query
                result_dict = enrich_with_aleph(result_dict, query_value, 'BE', 'company')

                output(result_dict)
            except ImportError as e:
                print(f"Error: Belgium module not available: {e}")
            except Exception as e:
                print(f"Error executing Belgium query: {e}")
            else:
                sys.exit(0)

    # =========================================================================
    # NORWAY OPERATOR MODE - Handle Norwegian operators (cno:, pno:)
    # =========================================================================
    if args.query:
        query_lower = args.query.strip().lower()
        no_operator_prefixes = ['cno:', 'pno:']

        if any(query_lower.startswith(prefix) for prefix in no_operator_prefixes):
            if not args.json:
                print(f"\n{'='*60}")
                print("NORWAY BRREG PUBLIC RECORDS SEARCH")
                print(f"{'='*60}")
                print(f"Query: {args.query}")
                print(f"{'='*60}\n")

            # Execute via Norway CLI
            try:
                from country_engines.NO.no_unified_cli import NOUnifiedCLI
                no_cli = NOUnifiedCLI()
                result = asyncio.run(no_cli.execute(args.query))
                result_dict = result.to_dict() if hasattr(result, 'to_dict') else result
                result_dict = add_graph_output(result_dict, result, "NO")

                # Enrich with OCCRP Aleph (Norway collections)
                query_value = args.query.split(':', 1)[1].strip() if ':' in args.query else args.query
                entity_type = 'person' if query_lower.startswith('pno:') else 'company'
                result_dict = enrich_with_aleph(result_dict, query_value, 'NO', entity_type)

                output(result_dict)
            except ImportError as e:
                print(f"Error: Norway module not available: {e}")
            except Exception as e:
                print(f"Error executing Norway query: {e}")
            else:
                sys.exit(0)

    # =========================================================================
    # FINLAND OPERATOR MODE - Handle Finnish operators (cfi:, pfi:)
    # =========================================================================
    if args.query:
        query_lower = args.query.strip().lower()
        fi_operator_prefixes = ['cfi:', 'pfi:']

        if any(query_lower.startswith(prefix) for prefix in fi_operator_prefixes):
            if not args.json:
                print(f"\n{'='*60}")
                print("FINLAND PRH PUBLIC RECORDS SEARCH")
                print(f"{'='*60}")
                print(f"Query: {args.query}")
                print(f"{'='*60}\n")

            # Execute via Finland CLI
            try:
                from country_engines.FI.fi_unified_cli import FIUnifiedCLI
                fi_cli = FIUnifiedCLI()
                result = asyncio.run(fi_cli.execute(args.query))
                result_dict = result.to_dict() if hasattr(result, 'to_dict') else result
                result_dict = add_graph_output(result_dict, result, "FI")

                # Enrich with OCCRP Aleph (Finland collections)
                query_value = args.query.split(':', 1)[1].strip() if ':' in args.query else args.query
                entity_type = 'person' if query_lower.startswith('pfi:') else 'company'
                result_dict = enrich_with_aleph(result_dict, query_value, 'FI', entity_type)

                output(result_dict)
            except ImportError as e:
                print(f"Error: Finland module not available: {e}")
            except Exception as e:
                print(f"Error executing Finland query: {e}")
            else:
                sys.exit(0)

    # =========================================================================
    # GLEIF OPERATOR MODE - Handle LEI lookups (lei:)
    # Global Legal Entity Identifier database - works for ALL countries
    # =========================================================================
    if args.query:
        query_lower = args.query.strip().lower()
        gleif_operator_prefixes = ['lei:']

        if any(query_lower.startswith(prefix) for prefix in gleif_operator_prefixes):
            if not args.json:
                print(f"\n{'='*60}")
                print("GLEIF LEI GLOBAL COMPANY SEARCH")
                print(f"{'='*60}")
                print(f"Query: {args.query}")
                print(f"{'='*60}\n")

            # Execute via GLEIF CLI
            try:
                from country_engines.GLEIF.gleif_cli import GLEIFUnifiedCLI
                gleif_cli = GLEIFUnifiedCLI()
                result = asyncio.run(gleif_cli.execute(args.query))
                result_dict = result.to_dict() if hasattr(result, 'to_dict') else result

                # Add graph output if available
                if result_dict.get('companies'):
                    result_dict['graph'] = {
                        'nodes': [],
                        'edges': []
                    }
                    for company in result_dict['companies'][:10]:
                        # Add company node
                        result_dict['graph']['nodes'].append({
                            'id': company.get('lei'),
                            'label': company.get('legal_name'),
                            'type': 'company',
                            'properties': {
                                'lei': company.get('lei'),
                                'jurisdiction': company.get('jurisdiction'),
                                'status': company.get('status'),
                                'legal_form': company.get('legal_form'),
                                'registry_id': company.get('registered_as')
                            }
                        })

                output(result_dict)
            except ImportError as e:
                print(f"Error: GLEIF module not available: {e}")
            except Exception as e:
                print(f"Error executing GLEIF query: {e}")
            else:
                sys.exit(0)

    # =========================================================================
    # SECTION-BASED ALEPH SEARCH - Handle reg{cc}:, lit{cc}:, ass{cc}:, cr{cc}: operators
    # For targeted searches by wiki section across ALL jurisdictions with Aleph collections
    # Examples: regde: (regulatory Germany), litus: (litigation US), assru: (assets Russia)
    # =========================================================================
    if args.query:
        query_lower = args.query.strip().lower()
        # Match section operators: reg{2-letter}, lit{2-letter}, ass{2-letter}, cr{2-letter}, leak{2-letter}, news{2-letter}
        section_match = re.match(r'^(reg|lit|ass|cr|leak|news)([a-z]{2}):\s*(.+)$', query_lower)

        if section_match:
            section_code = section_match.group(1)  # reg, lit, ass, cr, leak, news
            country_code = section_match.group(2).upper()  # DE, US, RU, etc.
            query_value = section_match.group(3).strip()

            # Map section to display name
            section_names = {
                'reg': 'REGULATORY',
                'lit': 'LITIGATION',
                'ass': 'ASSETS',
                'cr': 'CORPORATE REGISTRY',
                'leak': 'LEAKS & GREY LITERATURE',
                'news': 'NEWS & MEDIA'
            }
            section_name = section_names.get(section_code, section_code.upper())

            if not args.json:
                print(f"\n{'='*60}")
                print(f"{section_name} SEARCH - {country_code}")
                print(f"{'='*60}")
                print(f"Query: {query_value}")
                print(f"Section: {section_name}")
                print(f"Source: OCCRP Aleph collections")
                print(f"{'='*60}\n")

            # Build result with Aleph section search
            result_dict = {
                'query': query_value,
                'jurisdiction': country_code,
                'section': section_code,
                'section_name': section_name,
                'modules_run': [],
                'results': {},
                'errors': []
            }

            # Entity type depends on the query context (default to company for most sections)
            entity_type = 'company'

            # Enrich with section-filtered Aleph search
            result_dict = enrich_with_aleph(result_dict, query_value, country_code, entity_type, section_code)

            # Add graph output
            result_dict = add_graph_output(result_dict, result_dict, country_code)

            output(result_dict)
            sys.exit(0)

    # =========================================================================
    # EXECUTION MODE - Handle prefix operators (p:, c:, e:, t:, d:, u:, social media prefixes)
    # =========================================================================
    if args.query:
        entity_type, value, operator_jur = parse_prefix(args.query)

        # Use jurisdiction from operator if provided, otherwise from flag
        jurisdiction = operator_jur or args.jurisdiction

        # INTELLIGENCE MODE: Operator provided but NO value (e.g., atcr:)
        # Display everything we know about this category/jurisdiction
        if not value and (entity_type or jurisdiction):
            print(f"\n{'='*60}")
            print(f"INTELLIGENCE REPORT: {jurisdiction or 'GLOBAL'} / {entity_type.upper() if entity_type else 'ALL'}")
            print(f"{'='*60}")
            
            intel = router.get_full_intel(jurisdiction=jurisdiction, input_type=entity_type)
            
            if jurisdiction and intel["jurisdiction"]:
                jur = intel["jurisdiction"]
                print(f"\n🌍 JURISDICTION: {jur['code']}")
                print(f"   Success Rate: {jur.get('stats', {}).get('success_rate', 'Unknown')}")
                if jur.get('wisdom'):
                    print(f"   Wisdom: {jur['wisdom']}")

            if intel["applicable_sources"]:
                print(f"\n📚 SOURCES & WIKI WISDOM ({len(intel['applicable_sources'])}):")
                for src in intel["applicable_sources"]:
                    print(f"  • {src['name']}")
                    print(f"    URL: {src['url']}")
                    if src.get('search_template'):
                        print(f"    PREDICTABLE URL: {src['search_template']}")
                    if src.get('execution_script'):
                        print(f"    HOW: python3 {src['execution_script']}")
                    if src.get('friction'):
                        print(f"    FRICTION: {src['friction']}")
                    if src.get('intel'):
                        print(f"    WIKI TEXT: {src['intel']}")
                    if src.get('atoms'):
                        print(f"    ATOMS: {', '.join(src['atoms'])}")
                    print()
            
            if intel["playbooks"]:
                print(f"📦 STRATEGIC PLAYBOOKS ({len(intel['playbooks'])}):")
                for pb in intel["playbooks"]:
                    print(f"  - {pb['id']}: {pb['label']} (Success: {pb.get('success_rate', 'N/A')})")
            
            return

        # If no prefix, try to auto-detect type
        if entity_type is None:
            auto_type = detect_entity_type(value)
            if auto_type:
                entity_type = auto_type
                if entity_type == "linkedin_url":
                    value = normalize_linkedin_url(value)
                print(f"Auto-detected type: {entity_type}")
            else:
                # If we can't detect, show help
                print("Error: No prefix specified and cannot auto-detect entity type.")
                print("Use prefixes: p: (person), c: (company), e: (email), t: (phone), d: (domain), u: (username), li: (linkedin_url), liu: (linkedin_username)")
                print(f"\nExample: io_cli.py \"p: {value}\"")
                sys.exit(1)

        print(f"\n{'='*60}")
        print(f"IO INVESTIGATION: {entity_type.upper()}")
        print(f"{'='*60}")
        print(f"Target: {value}")
        if jurisdiction:
            print(f"Jurisdiction: {jurisdiction}")
        
        # DISPLAY CONSOLIDATED INTEL (The "Everything we know" view)
        intel = router.get_full_intel(jurisdiction=jurisdiction, input_type=entity_type)
        if not args.json:
            print(f"\nRESOURCES & WISDOM:")
            for src in intel["applicable_sources"][:10]: # Top 10
                print(f"  • {src['name']}")
                print(f"    URL: {src['url']}")
                if src.get('execution_script'):
                    print(f"    HOW: python3 {src['execution_script']}")
                if src.get('intel'):
                    print(f"    NOTE: {src['intel']}")
            
            if intel["playbooks"]:
                print(f"\nSTRATEGIC PLAYBOOKS: {len(intel['playbooks'])} found")
                for pb in intel["playbooks"][:3]:
                    print(f"  - {pb['id']}: {pb['label']}")

        if args.dry_run:
            print("\nMode: DRY RUN (showing plan only)")
        print(f"{'='*60}\n")

        # Initialize executor and run investigation
        executor = IOExecutor(router, dry_run=args.dry_run, project_id=args.project)

        # Run async execution
        if args.recurse:
            recurse_types = [t.strip() for t in (args.recurse_types or "").split(",") if t.strip()]
            result = asyncio.run(
                executor.execute_recursive(
                    entity_type,
                    value,
                    jurisdiction,
                    max_depth=args.max_depth,
                    max_nodes=args.max_nodes,
                    recurse_types=recurse_types,
                    persist_project=args.project,
                )
            )
        else:
            result = asyncio.run(executor.execute(entity_type, value, jurisdiction))
        output(result)

        # Show summary
        if not args.dry_run and not args.json:
            print(f"\n{'='*60}")
            print("SUMMARY")
            print(f"{'='*60}")
            print(f"Modules run: {', '.join(result.get('modules_run', []))}")
            if result.get('errors'):
                print(f"Errors: {len(result['errors'])}")
                for err in result['errors']:
                    print(f"  ⚠️  {err}")
            print(f"Duration: {result.get('duration_seconds', 0):.2f}s")

        # Results visualization (if requested)
        if args.results_viz and not args.dry_run:
            # Generate and open results visualization
            html = generate_results_viz_html(result)
            with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
                f.write(html)
                print(f"\n📊 Results Visualization: {f.name}")
                webbrowser.open(f'file://{f.name}')

    # =========================================================================
    # MODULE INFO MODE - List available modules
    # =========================================================================
    elif args.list_modules:
        modules = {
            "EYE-D": {
                "description": "OSINT lookup for persons, emails, phones",
                "entity_types": ["person", "email", "phone"],
                "location": "BACKEND/modules/EYE-D/unified_osint.py"
            },
            "Corporella": {
                "description": "Corporate registry lookups and company intelligence",
                "entity_types": ["company"],
                "location": "BACKEND/modules/corporella/"
            },
            "OpenSanctions": {
                "description": "PEP and sanctions screening",
                "entity_types": ["person", "company"],
                "api_key_required": "OPENSANCTIONS_API_KEY"
            },
            "OpenCorporates": {
                "description": "Global company registry data",
                "entity_types": ["company"],
                "api_key_required": "OPENCORPORATES_API_KEY (optional)"
            },
            "WHOIS": {
                "description": "Domain registration lookup",
                "entity_types": ["domain"],
                "location": "python-whois package"
            },
            "LINKLATER": {
                "description": "Link analysis, archives, entity extraction, file discovery via operator syntax",
                "entity_types": ["domain", "url", "keyword"],
                "location": "BACKEND/modules/query_executor.py"
            },
            "SocialMedia": {
                "description": "Targeted social media search (Facebook, Twitter/X, LinkedIn, Instagram, Threads)",
                "entity_types": ["person", "username", "company", "keyword"],
                "location": "BACKEND/modules/BRUTE/targeted_searches/community/social_media.py"
            },
            "BrightData": {
                "description": "SERP search (Google/Bing/Yandex) and web scraping with bot bypass",
                "entity_types": ["person", "company", "email", "phone", "domain", "brand", "product"],
                "api_key_required": "BRIGHTDATA_API_KEY",
                "capabilities": ["serp_search", "multi_search", "web_scrape"],
                "engines": ["google", "bing", "yandex"]
            }
        }
        if args.json:
            print(json.dumps(modules, indent=2))
        else:
            print("\nAvailable Execution Modules:")
            print("="*60)
            for name, info in modules.items():
                status = info.get('status', 'active')
                status_icon = "✅" if status == 'active' else "⏳"
                print(f"\n{status_icon} {name}")
                print(f"   {info['description']}")
                print(f"   Entity types: {', '.join(info['entity_types'])}")
                if 'api_key_required' in info:
                    print(f"   Requires: {info['api_key_required']}")

    elif args.module_info:
        module_name = args.module_info.lower()
        module_details = {
            "eye-d": {
                "name": "EYE-D",
                "description": "Unified OSINT search module",
                "capabilities": [
                    "Person search: social profiles, breach data, public records",
                    "Email search: reverse lookup, breach checks, associated accounts",
                    "Phone search: carrier info, reverse lookup"
                ],
                "methods": ["search_person()", "search_email()", "search_phone()"],
                "location": "BACKEND/modules/EYE-D/unified_osint.py"
            },
            "corporella": {
                "name": "Corporella",
                "description": "Corporate intelligence and registry lookup",
                "capabilities": [
                    "Company search across multiple registries",
                    "Neural search for company matching",
                    "News aggregation for companies"
                ],
                "methods": ["search_company()"],
                "location": "BACKEND/modules/corporella/exa_company_search.py"
            },
            "linklater": {
                "name": "LINKLATER",
                "description": "Operator-driven link analysis, archives, entity extraction, and file discovery",
                "capabilities": [
                    "Backlinks/outlinks (domain or page level)",
                    "Historical archive queries with year ranges",
                    "Entity extraction (persons, companies, emails, phones, addresses)",
                    "Filetype discovery (pdf, doc, word, xls, ppt)",
                    "Tor/onion search context"
                ],
                "operator_syntax": [
                    "?bl:!example.com",
                    "bl?:!example.com",
                    "ent?:2024! !example.com",
                    "pdf!:!example.com",
                    "\"keyword\" :tor"
                ],
                "location": "BACKEND/modules/query_executor.py"
            },
            "opensanctions": {
                "name": "OpenSanctions",
                "description": "PEP and sanctions screening via OpenSanctions API",
                "capabilities": [
                    "Person sanctions check",
                    "Company sanctions check",
                    "PEP (Politically Exposed Person) screening"
                ],
                "api_endpoint": "https://api.opensanctions.org/match/default",
                "api_key": "OPENSANCTIONS_API_KEY"
            },
            "social_media": {
                "name": "Social Media Targeted Search",
                "description": "Targeted social search across Facebook, Twitter/X, LinkedIn, Instagram, and Threads.",
                "capabilities": [
                    "Profile discovery via platform search endpoints",
                    "Keyword/content searches across platform verticals",
                    "Company/profile variants and Google dorks"
                ],
                "methods": ["search()", "search_person()", "search_username()", "search_company()"],
                "location": "BACKEND/modules/BRUTE/targeted_searches/community/social_media.py"
            }
        }
        info = module_details.get(module_name)
        if info:
            output(info)
        else:
            print(f"Unknown module: {args.module_info}")
            print(f"Available: {', '.join(module_details.keys())}")

    # =========================================================================
    # ROUTING MODE - Existing lookup capabilities
    # =========================================================================
    elif args.stats:
        output(router.get_stats())
    elif args.legend:
        results = router.search_legend(args.legend)
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            print(f"Found {len(results)} matching fields:")
            for r in results:
                print(f"  [{r['code']:3d}] {r['name']}")
    elif args.have and args.show_capabilities:
        output(router.find_capabilities(args.have))
        # Source viz removed - use --viz explicitly if needed
    elif args.have and args.want:
        # --have X --want Y automatically finds path (--find-path is implicit)
        output(router.find_route(args.have, args.want, args.depth))
        # Source viz removed - use --viz explicitly if needed
    elif args.graph:
        output(router.get_graph_data(args.graph, args.depth))
        # Source viz removed - use --viz explicitly if needed
    elif args.viz:
        # EXPLICIT source capability visualization (opt-in only)
        graph_data = router.get_graph_data(args.viz, args.depth)
        if "error" in graph_data:
            print(f"Error: {graph_data['error']}")
            sys.exit(1)
        html = generate_viz_html(graph_data, router)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
            f.write(html)
            print(f"Source Capability Graph: {f.name}")
            webbrowser.open(f'file://{f.name}')
    elif args.have:
        # Just --have shows capabilities (no auto-viz - use --viz for that)
        output(router.find_capabilities(args.have))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
