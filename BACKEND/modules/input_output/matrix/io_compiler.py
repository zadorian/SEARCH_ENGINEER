#!/usr/bin/env python3
"""
IO Compiler - The Librarian: Loads the NORMALIZED Canonical Files.

SINGLE SOURCE OF TRUTH ARCHITECTURE:

1. sources.json      - PRIMARY SOURCES (ID = domain or collection name)
                       11,516 unique sources, each with: name, jurisdictions[], inputs[], outputs[], handled_by

2. modules.json      - OUR MODULES (ID = module name: eye-d, corporella, torpedo)
                       6 modules with: path, inputs[], outputs[], aggregators[]

3. codes.json        - THE LEGEND (ID = numeric code)
                       401 field codes with: name, type, creates (node/edge/metadata)

4. jurisdictions.json - COUNTRY METADATA (ID = ISO code)
                       161 jurisdictions, REFERENCES sources via source_domains[]

5. methodologies.json - Research patterns
6. genres.json        - Report types
7. sectors.json       - Industry intelligence
8. output_graph_rules.json - Graph creation rules (Pivot Principle)

KEY PRINCIPLE: References, not embeddings. No duplication.

Usage:
    compiler = IOCompiler()
    manifest = compiler.compile()

    # Get source by domain (THE ID)
    source = compiler.get_source_by_domain("companieshouse.gov.uk")

    # Get all sources for a jurisdiction
    sources = compiler.get_sources_for_jurisdiction("GB")

    # Get module that handles a source
    module = compiler.get_module("corporella")

    # Get graph rules for an output code
    graph_ops = compiler.get_graph_rules_for_code(59)
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)

MATRIX_DIR = Path(__file__).parent
BACKEND_DIR = MATRIX_DIR.parent.parent / "BACKEND" / "modules"


@dataclass
class UnifiedSource:
    """
    Every source knows its domain (THE ID), jurisdictions, handler, and I/O codes.

    This is THE canonical representation after compilation.
    ID = domain (e.g., "companieshouse.gov.uk") or collection name (e.g., "linkedin-2021-breach")
    """

    # Identity - domain IS the ID
    id: str                          # e.g., "companieshouse.gov.uk" (THE domain)
    name: str                        # e.g., "Companies House"
    domain: str = ""                 # Same as id for web sources
    jurisdictions: List[str] = field(default_factory=list)  # e.g., ["GB"] or ["GLOBAL"]

    # Classification
    source_type: str = ""            # e.g., "registry", "api", "breach"
    category: str = ""               # e.g., "corporate_registry"
    classification: str = ""         # e.g., "Official Registry"
    friction: str = ""               # "open" | "paywalled" | "restricted"

    # URLs
    url: str = ""                    # Registry home URL
    search_url: str = ""             # Search template URL

    # I/O Codes (references codes.json)
    inputs: List[int] = field(default_factory=list)   # What codes it accepts
    outputs: List[int] = field(default_factory=list)  # What codes it returns

    # Execution - which MODULE handles this (references modules.json)
    handled_by: str = ""             # "corporella" | "eye-d" | "torpedo" | "alldom"
    execution_script: Optional[str] = None  # Path to .py file (optional)

    # Intelligence
    reliability: Optional[Dict] = None  # {success_rate, avg_latency, test_count}

    # Legacy fields (for compatibility)
    search_tips: str = ""
    access_notes: str = ""
    quirks: List[str] = field(default_factory=list)
    dead_end_actions: Dict[str, str] = field(default_factory=dict)
    arbitrage_from: List[str] = field(default_factory=list)
    bangs: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for JSON serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "domain": self.domain,
            "jurisdictions": self.jurisdictions,
            "source_type": self.source_type,
            "category": self.category,
            "classification": self.classification,
            "friction": self.friction,
            "url": self.url,
            "search_url": self.search_url,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "handled_by": self.handled_by,
            "execution_script": self.execution_script,
            "reliability": self.reliability,
        }

    @property
    def jurisdiction(self) -> str:
        """Legacy compatibility: return first jurisdiction."""
        return self.jurisdictions[0] if self.jurisdictions else ""


class IOCompiler:
    """
    The Librarian - Aggregates the Manifest from all JSON/Wiki files.

    Compile once at startup, then query the unified manifest.
    """

    def __init__(self):
        # Primary manifest: domain -> UnifiedSource
        self._manifest: Dict[str, UnifiedSource] = {}

        # Indexes
        self._by_jurisdiction: Dict[str, List[str]] = {}  # jur -> [domains]
        self._by_category: Dict[str, List[str]] = {}      # cat -> [domains]

        # Modules (our code)
        self._modules: Dict[str, Dict] = {}               # module_id -> module_data

        # Codes legend
        self._codes: Dict[str, Dict] = {}                 # code_str -> {name, type, creates, ...}

        # Jurisdiction metadata (not source data!)
        self._jurisdictions: Dict[str, Dict] = {}         # jur_code -> metadata

        # Legacy compatibility
        self._jurisdiction_aliases: Dict[str, str] = {}
        self._bangs_by_trigger: Dict[str, str] = {}
        self._compiled: bool = False

        # Other canonical data
        self._methodology: Dict[str, Any] = {}
        self._genres: Dict[str, Any] = {}
        self._section_templates: Dict[str, Any] = {}
        self._sectors: Dict[str, Any] = {}
        self._graph_rules: Dict[str, Any] = {}
        self._dead_ends: Dict[str, List] = {}
        self._arbitrage_paths: Dict[str, List] = {}

    def compile(self) -> Dict[str, UnifiedSource]:
        """
        Build the unified manifest at runtime.

        Returns:
            Dict mapping domain -> UnifiedSource
        """
        if self._compiled:
            return self._manifest

        logger.info("IOCompiler: Loading NORMALIZED canonical files...")

        # 1. Load codes.json (THE LEGEND - must load first)
        self._load_codes()
        logger.info(f"  1. codes.json: {len(self._codes)} field codes")

        # 2. Load modules.json (OUR CODE)
        self._load_modules()
        logger.info(f"  2. modules.json: {len(self._modules)} modules")

        # 3. Load sources.json (PRIMARY SOURCES - ID = domain)
        self._load_sources_canonical()
        logger.info(f"  3. sources.json: {len(self._manifest)} sources")

        # 4. Load jurisdictions.json (METADATA only, references sources)
        self._load_jurisdictions()
        logger.info(f"  4. jurisdictions.json: {len(self._jurisdictions)} jurisdictions")

        # 5. Load methodology patterns
        self._load_methodology()
        logger.info(f"  5. methodologies.json: loaded")

        # 6. Load genres
        self._load_genres()
        logger.info(f"  6. genres.json: loaded")

        # 7. Load sectors
        self._load_sectors()
        logger.info(f"  7. sectors.json: {len(self._sectors.get('sectors', {}))} sectors")

        # 8. Load graph rules (Pivot Principle)
        self._load_graph_rules()
        logger.info(f"  8. output_graph_rules.json: loaded")

        # 9. Link execution scripts to sources
        self._link_execution_scripts()

        self._compiled = True
        logger.info(f"IOCompiler: Complete. {len(self._manifest)} sources, {len(self._modules)} modules, {len(self._by_jurisdiction)} jurisdictions")

        return self._manifest

    # =========================================================================
    # CANONICAL FILE LOADERS (NORMALIZED SCHEMA)
    # =========================================================================

    def _load_codes(self):
        """Load codes.json - THE LEGEND for all field codes."""
        path = MATRIX_DIR / "codes.json"
        if not path.exists():
            logger.warning(f"codes.json not found")
            return

        with open(path) as f:
            data = json.load(f)

        self._codes = data.get("codes", {})

    def _load_modules(self):
        """Load modules.json - OUR MODULES (eye-d, corporella, torpedo, etc.)."""
        path = MATRIX_DIR / "modules.json"
        if not path.exists():
            logger.warning(f"modules.json not found")
            return

        with open(path) as f:
            data = json.load(f)

        self._modules = data.get("modules", {})

    def _load_sources_canonical(self):
        """
        Load PRIMARY SOURCES from split files in matrix/sources/*.json.
        This enforces the split files as the Single Source of Truth.
        """
        sources_dir = MATRIX_DIR / "sources"
        if not sources_dir.exists():
            logger.warning(f"Sources directory not found at {sources_dir}")
            return

        loaded_count = 0
        
        # Iterate over all JSON files in sources directory
        for source_file in sources_dir.glob("*.json"):
            try:
                with open(source_file) as f:
                    data = json.load(f)
                
                # Check if file follows jurisdiction-grouped structure (like corporate_registries.json)
                # Structure: {"DE": [source1, source2], "FR": [...]}
                if isinstance(data, dict) and not source_file.name.startswith("legacy"):
                    for jur, sources in data.items():
                        if isinstance(sources, list):
                            for source in sources:
                                self._add_source_to_manifest(source)
                                loaded_count += 1
                                
                # Check if file is a flat list (legacy structure)
                elif isinstance(data, list):
                    for source in data:
                        self._add_source_to_manifest(source)
                        loaded_count += 1
                        
            except Exception as e:
                logger.error(f"Failed to load source file {source_file.name}: {e}")

        logger.info(f"Loaded {loaded_count} sources from {len(list(sources_dir.glob('*.json')))} split files")

    def _add_source_to_manifest(self, source: Dict):
        """Helper to add a raw source dict to the manifest."""
        domain = source.get("domain") or source.get("id")
        if not domain:
            return

        # Ensure ID is set
        if "id" not in source:
            source["id"] = domain

        unified = UnifiedSource(
            id=source["id"],
            name=source.get("name", domain),
            domain=domain,
            jurisdictions=source.get("jurisdictions", [source.get("jurisdiction", "GLOBAL")]),
            source_type=source.get("type", ""),
            category=source.get("category", ""),
            classification=source.get("classification", ""),
            friction=source.get("friction", ""),
            url=source.get("url", ""),
            search_url=source.get("search_url", ""),
            inputs=source.get("inputs", []),
            outputs=source.get("outputs", []),
            handled_by=source.get("handled_by", ""),
            reliability=source.get("reliability"),
            # Legacy fields
            search_tips=source.get("search_tips", ""),
            access_notes=source.get("access_notes", ""),
            quirks=source.get("quirks", []),
            bangs=source.get("bangs", []),
        )

        self._manifest[domain] = unified

        # Index by category
        cat = unified.category
        if cat:
            if cat not in self._by_category:
                self._by_category[cat] = []
            self._by_category[cat].append(domain)
            
        # Index by jurisdiction
        for jur in unified.jurisdictions:
            if jur not in self._by_jurisdiction:
                self._by_jurisdiction[jur] = []
            if domain not in self._by_jurisdiction[jur]:
                self._by_jurisdiction[jur].append(domain)

    def _load_jurisdictions(self):
        """
        Load jurisdictions.json - JURISDICTION METADATA.

        Contains: legal_notes, entity_types, id_formats, source_domains[]
        Does NOT contain embedded source data - only REFERENCES.
        """
        path = MATRIX_DIR / "jurisdictions.json"
        if not path.exists():
            logger.warning(f"jurisdictions.json not found")
            return

        with open(path) as f:
            data = json.load(f)

        self._jurisdictions = data.get("jurisdictions", {})

    def _load_jurisdiction_intel(self):
        """Load CANONICAL jurisdiction_intel.json (consolidated intel)."""
        intel_path = MATRIX_DIR / "jurisdiction_intel.json"
        if not intel_path.exists():
            return

        with open(intel_path) as f:
            data = json.load(f)

        self._jurisdiction_intel = data.get("jurisdictions", {})

        # Graft dead ends and arbitrage onto sources
        for jur_code, intel in self._jurisdiction_intel.items():
            # Add dead ends to sources
            dead_ends = intel.get("dead_ends", [])
            for de in dead_ends:
                sought = de.get("sought", "")
                reason = de.get("reason", "")
                for source_id in self._by_jurisdiction.get(jur_code, []):
                    source = self._manifest.get(source_id)
                    if source and sought:
                        source.dead_end_actions[sought] = reason

            # Add arbitrage paths
            arb_paths = intel.get("arbitrage_paths", {})
            for source_id in self._by_jurisdiction.get(jur_code, []):
                source = self._manifest.get(source_id)
                if source:
                    if isinstance(arb_paths, dict):
                        source.arbitrage_from = list(arb_paths.keys())
                    elif isinstance(arb_paths, list):
                        source.arbitrage_from = [str(p) for p in arb_paths[:5]]  # Limit

    def _load_methodology(self):
        """Load methodologies.json (research patterns)."""
        path = MATRIX_DIR / "methodologies.json"
        if not path.exists():
            # Try old name for compatibility
            path = MATRIX_DIR / "methodology.json"
            if not path.exists():
                return

        with open(path) as f:
            self._methodology = json.load(f)

    def _load_genres(self):
        """Load CANONICAL genres.json."""
        path = MATRIX_DIR / "genres.json"
        if not path.exists():
            return

        with open(path) as f:
            self._genres = json.load(f)

    def _load_section_templates(self):
        """Load CANONICAL section_templates.json."""
        path = MATRIX_DIR / "section_templates.json"
        if not path.exists():
            return

        with open(path) as f:
            self._section_templates = json.load(f)

    def _load_sectors(self):
        """Load CANONICAL sectors.json."""
        path = MATRIX_DIR / "sectors.json"
        if not path.exists():
            return

        with open(path) as f:
            self._sectors = json.load(f)

    def _load_graph_rules(self):
        """Load CANONICAL output_graph_rules.json (Pivot Principle)."""
        path = MATRIX_DIR / "output_graph_rules.json"
        if not path.exists():
            return

        with open(path) as f:
            self._graph_rules = json.load(f)

    def _load_legend(self):
        """Load legend.json (field code definitions)."""
        path = MATRIX_DIR / "legend.json"
        if not path.exists():
            return

        with open(path) as f:
            self._legend = json.load(f)

    # =========================================================================
    # LEGACY LOADERS (kept for compatibility, will be deprecated)
    # =========================================================================

    def _load_sources_v4(self):
        """DEPRECATED: Use _load_sources_canonical instead."""
        return self._load_sources_canonical()

    def _load_jurisdiction_aliases(self):
        """Load jurisdiction aliases for legacy code resolution."""
        aliases_path = MATRIX_DIR / "jurisdiction_aliases.json"
        if not aliases_path.exists():
            return

        with open(aliases_path) as f:
            self._jurisdiction_aliases = json.load(f)

    def _graft_wiki_sections(self):
        """Graft wiki wisdom onto sources."""
        wiki_path = MATRIX_DIR / "wiki_sections_processed.json"
        if not wiki_path.exists():
            return

        with open(wiki_path) as f:
            data = json.load(f)

        # Structure: jurisdictions -> code -> {wiki_file, sections}
        jurisdictions = data.get("jurisdictions", {})

        for jur_code, jur_data in jurisdictions.items():
            self._wiki_sections[jur_code] = jur_data

            sections = jur_data.get("sections", {})

            # Graft corporate_registry info to corporate registry sources
            if "corporate_registry" in sections:
                cr_info = sections["corporate_registry"]
                for source_id in self._by_jurisdiction.get(jur_code, []):
                    source = self._manifest.get(source_id)
                    if source and source.category in ("corporate_registry", "company_registry"):
                        source.search_tips = cr_info.get("summary", "")
                        source.access_notes = cr_info.get("access_notes", "")

    def _graft_investigation_notes(self):
        """Graft investigation notes (archived dead ends from rules)."""
        notes_path = MATRIX_DIR / "investigation_notes.json"
        if not notes_path.exists():
            return

        with open(notes_path) as f:
            data = json.load(f)

        # Structure: archived_dead_ends -> list of rules with notes
        dead_ends = data.get("archived_dead_ends", [])

        for rule in dead_ends:
            jurisdiction = rule.get("jurisdiction", "")
            notes = rule.get("notes", "")
            attempted = rule.get("attempted_sources", [])

            if not jurisdiction:
                continue

            # Add to sources in this jurisdiction as quirks
            for source_id in self._by_jurisdiction.get(jurisdiction, []):
                source = self._manifest.get(source_id)
                if source:
                    if notes and notes not in source.quirks:
                        source.quirks.append(notes)

    def _graft_dead_ends(self):
        """Graft dead ends catalog onto sources."""
        dead_ends_path = MATRIX_DIR / "_merged" / "dead_ends_catalog.json"
        if not dead_ends_path.exists():
            return

        with open(dead_ends_path) as f:
            data = json.load(f)

        # Structure: by_jurisdiction -> {jurisdiction -> [{sought, reason, attempted_sources}]}
        by_jurisdiction = data.get("by_jurisdiction", {})

        self._dead_ends = by_jurisdiction

        for jurisdiction, dead_ends_list in by_jurisdiction.items():
            for dead_end in dead_ends_list:
                sought = dead_end.get("sought", "")
                reason = dead_end.get("reason", "")

                # Add to all sources in this jurisdiction
                for source_id in self._by_jurisdiction.get(jurisdiction, []):
                    source = self._manifest.get(source_id)
                    if source and sought:
                        source.dead_end_actions[sought] = reason

    def _graft_arbitrage_paths(self):
        """Graft arbitrage paths for cross-border data access."""
        arb_path = MATRIX_DIR / "arbitrage_paths.json"
        if not arb_path.exists():
            return

        with open(arb_path) as f:
            data = json.load(f)

        self._arbitrage_paths = data

        # Structure varies - look for paths that indicate alternative sources
        # For now, store raw data for lookup

    def _graft_jurisdiction_intel(self):
        """Graft jurisdiction intelligence (capabilities, success rates)."""
        intel_path = MATRIX_DIR / "jurisdiction_intel.json"
        if not intel_path.exists():
            return

        with open(intel_path) as f:
            data = json.load(f)

        # Structure: by_region categorization
        # Extract any source-level intelligence

    def _index_bangs(self):
        """Index bangs for quick lookup."""
        # Try all_bangs.json
        bangs_path = MATRIX_DIR.parent.parent / "BACKEND" / "domain_sources" / "bangs" / "indexes" / "master_bang_index.json"
        if not bangs_path.exists():
            bangs_path = MATRIX_DIR.parent.parent / "BACKEND" / "domain_sources" / "all_bangs.json"

        if not bangs_path.exists():
            return

        try:
            with open(bangs_path) as f:
                data = json.load(f)

            # Index by trigger
            if isinstance(data, list):
                for bang in data:
                    trigger = bang.get("t", bang.get("trigger", ""))
                    domain = bang.get("d", bang.get("domain", ""))
                    if trigger and domain:
                        self._bangs_by_trigger[trigger] = domain
                        # Link bang to source by domain
                        if domain in self._by_domain:
                            source_id = self._by_domain[domain]
                            source = self._manifest.get(source_id)
                            if source:
                                source.bangs.append(f"!{trigger}")
            elif isinstance(data, dict):
                for trigger, info in data.items():
                    domain = info.get("domain", "") if isinstance(info, dict) else info
                    if trigger and domain:
                        self._bangs_by_trigger[trigger] = domain
        except Exception as e:
            logger.warning(f"Failed to load bangs: {e}")

    def _link_execution_scripts(self):
        """Link execution scripts from country_engines to sources."""
        engines_dir = BACKEND_DIR / "country_engines"
        if not engines_dir.exists():
            return

        # Look for jurisdiction-specific scripts
        for script_path in engines_dir.glob("*/*.py"):
            # Parse jurisdiction from path (e.g., AT/at_corporate.py -> AT)
            jurisdiction = script_path.parent.name.upper()

            # Link to sources in this jurisdiction
            for source_id in self._by_jurisdiction.get(jurisdiction, []):
                source = self._manifest.get(source_id)
                if source and not source.execution_script:
                    source.execution_script = str(script_path)
                    source.handler_type = "torpedo"  # Default handler

    # ==========================================================================
    # PUBLIC API
    # ==========================================================================

    def get_source(self, domain: str) -> Optional[UnifiedSource]:
        """
        Get source by domain (THE ID).

        Example:
            source = compiler.get_source("companieshouse.gov.uk")
        """
        self.compile()
        return self._manifest.get(domain)

    def get_source_by_domain(self, domain: str) -> Optional[UnifiedSource]:
        """Alias for get_source - domain IS the ID."""
        return self.get_source(domain)

    def get_sources_for_jurisdiction(self, jurisdiction: str) -> List[UnifiedSource]:
        """Get all sources available for a jurisdiction."""
        self.compile()

        # Try to resolve alias
        resolved = self._jurisdiction_aliases.get(jurisdiction, jurisdiction)

        domains = self._by_jurisdiction.get(resolved, [])
        return [self._manifest[d] for d in domains if d in self._manifest]

    def get_sources_for_category(self, category: str) -> List[UnifiedSource]:
        """Get all sources in a category."""
        self.compile()
        domains = self._by_category.get(category, [])
        return [self._manifest[d] for d in domains if d in self._manifest]

    def get_module(self, module_id: str) -> Optional[Dict]:
        """
        Get module by ID (eye-d, corporella, torpedo, etc.).

        Example:
            module = compiler.get_module("corporella")
            # Returns: {name, path, inputs, outputs, aggregators}
        """
        self.compile()
        return self._modules.get(module_id)

    def get_code(self, code: int) -> Optional[Dict]:
        """
        Get code definition from THE LEGEND.

        Example:
            code_info = compiler.get_code(13)
            # Returns: {name: "company_name", type: "entity", creates: "node", ...}
        """
        self.compile()
        return self._codes.get(str(code))

    def get_code_name(self, code: int) -> str:
        """Get the field name for a code."""
        code_info = self.get_code(code)
        return code_info.get("name", f"unknown_{code}") if code_info else f"unknown_{code}"

    def get_jurisdiction_metadata(self, jurisdiction: str) -> Dict:
        """
        Get jurisdiction metadata (legal notes, entity types, etc.).

        This is METADATA only, not source data.
        """
        self.compile()
        resolved = self._jurisdiction_aliases.get(jurisdiction, jurisdiction)
        return self._jurisdictions.get(resolved, {})

    def get_sources_for_module(self, module_id: str) -> List[UnifiedSource]:
        """Get all sources handled by a specific module."""
        self.compile()
        return [s for s in self._manifest.values() if s.handled_by == module_id]

    def get_wiki_for_jurisdiction(self, jurisdiction: str) -> Dict:
        """Get jurisdiction metadata (alias for get_jurisdiction_metadata)."""
        return self.get_jurisdiction_metadata(jurisdiction)

    def get_dead_ends_for_jurisdiction(self, jurisdiction: str) -> List[Dict]:
        """Get dead ends for a jurisdiction."""
        self.compile()
        resolved = self._jurisdiction_aliases.get(jurisdiction, jurisdiction)
        return self._dead_ends.get(resolved, [])

    def get_arbitrage_paths(self, jurisdiction: str) -> List[Dict]:
        """Get alternative routes for data access."""
        self.compile()
        resolved = self._jurisdiction_aliases.get(jurisdiction, jurisdiction)
        return self._arbitrage_paths.get(resolved, [])

    def resolve_bang(self, bang: str) -> Optional[str]:
        """Resolve a bang trigger to domain."""
        self.compile()
        # Strip leading ! if present
        trigger = bang.lstrip("!")
        return self._bangs_by_trigger.get(trigger)

    def resolve_jurisdiction(self, code: str) -> str:
        """Resolve a jurisdiction code (including legacy aliases)."""
        self.compile()
        return self._jurisdiction_aliases.get(code, code)

    def get_source_for_rule(self, rule_id: str) -> Optional[UnifiedSource]:
        """
        Get source for a rule ID (used by SourceNameResolver).

        Parses rule_id like "COMPANY_OFFICERS_HU" to find jurisdiction and category.
        """
        self.compile()

        # Parse rule ID
        parts = rule_id.upper().split("_")

        # Last part is often jurisdiction
        potential_jur = parts[-1] if parts else ""
        resolved_jur = self.resolve_jurisdiction(potential_jur)

        # Get sources for jurisdiction
        sources = self.get_sources_for_jurisdiction(resolved_jur)

        # Try to match by category from rule name
        if "OFFICER" in rule_id or "DIRECTOR" in rule_id:
            for s in sources:
                if s.category in ("corporate_registry", "company_registry"):
                    return s
        elif "SHAREHOLDER" in rule_id or "OWNERSHIP" in rule_id:
            for s in sources:
                if s.category in ("corporate_registry", "company_registry", "ownership_registry"):
                    return s
        elif "LITIGATION" in rule_id or "COURT" in rule_id:
            for s in sources:
                if s.category in ("litigation", "court_records"):
                    return s

        # Return first source for jurisdiction as fallback
        return sources[0] if sources else None

    # ==========================================================================
    # CANONICAL DATA ACCESSORS
    # ==========================================================================

    def get_graph_rules_for_code(self, code: int) -> Dict[str, Any]:
        """
        Get graph creation rules for an output field code (Pivot Principle).

        Returns what node/edge to create when this code is returned by a rule.

        Example:
            rules = compiler.get_graph_rules_for_code(59)  # company_officer_name
            # Returns: {
            #   "node_type": "person",
            #   "edge_type": "officer_of",
            #   "edge_source": 59,
            #   "edge_target": 13,
            #   "metadata_codes": [60, 61, 62]
            # }
        """
        self.compile()
        code_str = str(code)

        # Get field name from codes
        code_info = self._codes.get(code_str, {})
        field_name = code_info.get("name", f"unknown_{code}") if isinstance(code_info, dict) else f"unknown_{code}"

        result = {
            "code": code,
            "field_name": field_name,
            "creates_node": False,
            "creates_edge": False,
            "is_metadata": False,
        }

        # Check node-creating codes
        node_rules = self._graph_rules.get("node_creating_codes", {})
        if code_str in node_rules:
            result["creates_node"] = True
            result["node_type"] = node_rules[code_str].get("node_type")
            result["label_from"] = node_rules[code_str].get("label_from")

        # Check edge-creating codes
        edge_rules = self._graph_rules.get("edge_creating_codes", {})
        if code_str in edge_rules:
            result["creates_edge"] = True
            result["edge_type"] = edge_rules[code_str].get("edge_type")
            result["edge_source_code"] = edge_rules[code_str].get("source_node_code")
            result["edge_target_code"] = edge_rules[code_str].get("target_node_code")
            result["edge_metadata_codes"] = edge_rules[code_str].get("metadata_codes", [])

        # Check metadata codes
        metadata_rules = self._graph_rules.get("metadata_codes", {})
        if code_str in metadata_rules:
            result["is_metadata"] = True
            result["property_name"] = metadata_rules[code_str].get("property")
            result["attach_to"] = metadata_rules[code_str].get("attach_to")

        return result

    def get_composite_rules(self, code: int) -> Optional[Dict[str, Any]]:
        """Get composite processing rules for array outputs like company_officers."""
        self.compile()
        composites = self._graph_rules.get("composite_rules", {})
        return composites.get(str(code))

    def get_sector_intel(self, sector_name: str) -> Dict[str, Any]:
        """
        Get sector-specific intelligence (red flags, typical structures).

        Example:
            intel = compiler.get_sector_intel("energy_trading")
            # Returns red flags like "complex multi-jurisdictional ownership"
        """
        self.compile()
        sectors = self._sectors.get("sectors", {})

        # Normalize sector name
        normalized = sector_name.lower().replace(" ", "_")
        return sectors.get(normalized, {})

    def get_section_template(self, section_type: str) -> List[Dict]:
        """
        Get templates for a section type.

        Example:
            templates = compiler.get_section_template("ownership_analysis")
            # Returns typical content, data sources, key phrases
        """
        self.compile()
        templates_by_type = self._section_templates.get("templates_by_type", {})
        return templates_by_type.get(section_type, [])

    def get_methodology_for_type(self, method_type: str) -> Dict[str, Any]:
        """
        Get methodology patterns for a research method type.

        Example:
            patterns = compiler.get_methodology_for_type("corporate_registry_search")
        """
        self.compile()
        patterns_by_jur = self._methodology.get("patterns_by_jurisdiction", {})

        # Aggregate all patterns matching this method type
        matching = []
        for jur, patterns in patterns_by_jur.items():
            for p in patterns:
                if p.get("method_type") == method_type:
                    matching.append(p)

        return {
            "method_type": method_type,
            "count": self._methodology.get("method_counts", {}).get(method_type, 0),
            "patterns": matching[:20]  # Limit for performance
        }

    def get_genre(self, genre_name: str) -> Dict[str, Any]:
        """
        Get report genre information.

        Example:
            genre = compiler.get_genre("due_diligence")
        """
        self.compile()
        primary = self._genres.get("primary_types", {})
        secondary = self._genres.get("secondary_types", {})

        return {
            "name": genre_name,
            "count_as_primary": primary.get(genre_name, 0),
            "count_as_secondary": secondary.get(genre_name, 0),
        }

    def get_jurisdiction_intel(self, jurisdiction: str) -> Dict[str, Any]:
        """
        Get comprehensive intelligence for a jurisdiction.

        Includes: data_availability, legal_notes, dead_ends, arbitrage_paths
        """
        self.compile()
        resolved = self._jurisdiction_aliases.get(jurisdiction, jurisdiction)
        return self._jurisdiction_intel.get(resolved, {})

    def get_all_sectors(self) -> List[str]:
        """Get list of all known sectors."""
        self.compile()
        sectors = self._sectors.get("sectors", {})
        return list(sectors.keys())

    def get_all_section_types(self) -> List[str]:
        """Get list of all section types."""
        self.compile()
        return list(self._section_templates.get("templates_by_type", {}).keys())

    def to_json(self) -> str:
        """Export manifest as JSON."""
        self.compile()
        return json.dumps(
            {sid: s.to_dict() for sid, s in self._manifest.items()},
            indent=2
        )


# =============================================================================
# CLI
# =============================================================================

def main():
    """CLI for testing IOCompiler."""
    import argparse

    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="IO Compiler - Build Unified Manifest")
    parser.add_argument("--source", "-s", help="Get specific source by ID")
    parser.add_argument("--jurisdiction", "-j", help="Get sources for jurisdiction")
    parser.add_argument("--category", "-c", help="Get sources for category")
    parser.add_argument("--wiki", "-w", help="Get wiki for source or jurisdiction")
    parser.add_argument("--dead-ends", "-d", help="Get dead ends for jurisdiction")
    parser.add_argument("--stats", action="store_true", help="Show compilation stats")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    compiler = IOCompiler()
    manifest = compiler.compile()

    if args.stats:
        print(f"\n{'='*60}")
        print("IO Compiler - Manifest Statistics")
        print(f"{'='*60}")
        print(f"Total Sources: {len(manifest)}")
        print(f"Jurisdictions: {len(compiler._by_jurisdiction)}")
        print(f"Categories: {len(compiler._by_category)}")
        print(f"Bangs: {len(compiler._bangs_by_trigger)}")
        print(f"Aliases: {len(compiler._jurisdiction_aliases)}")
        print(f"\nTop Jurisdictions by Source Count:")
        sorted_jurs = sorted(compiler._by_jurisdiction.items(), key=lambda x: -len(x[1]))[:10]
        for jur, ids in sorted_jurs:
            print(f"  {jur}: {len(ids)} sources")
        print(f"\nCategories:")
        for cat, ids in sorted(compiler._by_category.items(), key=lambda x: -len(x[1])):
            print(f"  {cat}: {len(ids)} sources")

    elif args.source:
        source = compiler.get_source(args.source)
        if source:
            if args.json:
                print(json.dumps(source.to_dict(), indent=2))
            else:
                print(f"\n{'='*60}")
                print(f"Source: {source.name}")
                print(f"{'='*60}")
                print(f"ID: {source.id}")
                print(f"Jurisdiction: {source.jurisdiction}")
                print(f"Category: {source.category}")
                print(f"URL: {source.url}")
                print(f"Domain: {source.domain}")
                print(f"Search Template: {source.search_template}")
                print(f"Handler: {source.handler_type}")
                print(f"Script: {source.execution_script}")
                if source.search_tips:
                    print(f"\nSearch Tips: {source.search_tips[:200]}...")
                if source.quirks:
                    print(f"\nQuirks: {source.quirks}")
                if source.bangs:
                    print(f"Bangs: {source.bangs}")
                if source.dead_end_actions:
                    print(f"\nDead Ends: {source.dead_end_actions}")
        else:
            print(f"Source not found: {args.source}")

    elif args.jurisdiction:
        sources = compiler.get_sources_for_jurisdiction(args.jurisdiction)
        if args.json:
            print(json.dumps([s.to_dict() for s in sources], indent=2))
        else:
            print(f"\n{'='*60}")
            print(f"Sources for {args.jurisdiction}: {len(sources)}")
            print(f"{'='*60}")
            for s in sources:
                print(f"  {s.id}: {s.name} ({s.category})")

    elif args.category:
        sources = compiler.get_sources_for_category(args.category)
        if args.json:
            print(json.dumps([s.to_dict() for s in sources], indent=2))
        else:
            print(f"\n{'='*60}")
            print(f"Sources for category {args.category}: {len(sources)}")
            print(f"{'='*60}")
            for s in sources:
                print(f"  {s.id}: {s.name} ({s.jurisdiction})")

    elif args.wiki:
        # Try as source ID first, then jurisdiction
        wiki = compiler.get_wiki_for_source(args.wiki)
        if not wiki.get("search_tips"):
            wiki = compiler.get_wiki_for_jurisdiction(args.wiki)

        if args.json:
            print(json.dumps(wiki, indent=2))
        else:
            print(f"\n{'='*60}")
            print(f"Wiki for {args.wiki}")
            print(f"{'='*60}")
            for k, v in wiki.items():
                print(f"{k}: {v}")

    elif args.dead_ends:
        dead_ends = compiler.get_dead_ends_for_jurisdiction(args.dead_ends)
        if args.json:
            print(json.dumps(dead_ends, indent=2))
        else:
            print(f"\n{'='*60}")
            print(f"Dead Ends for {args.dead_ends}: {len(dead_ends)}")
            print(f"{'='*60}")
            for de in dead_ends:
                print(f"  Sought: {de.get('sought')}")
                print(f"  Reason: {de.get('reason')}")
                print()

    else:
        # Default: show stats
        print(f"Compiled {len(manifest)} unified sources")
        print("Use --stats, --source, --jurisdiction, --category, --wiki, or --dead-ends")


if __name__ == "__main__":
    main()
