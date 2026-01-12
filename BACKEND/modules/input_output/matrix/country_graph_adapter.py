#!/usr/bin/env python3
"""
Country Graph Adapter - Standardized Node/Edge Creation from Country CLIs

Maps outputs from UK, NO, FI, CH, IE, BE, CZ, and GLEIF (global) to standard graph operations.

PHILOSOPHY:
1. Each country CLI returns jurisdiction-specific data structures
2. This adapter normalizes them to standard node types and edge types
3. Uses relationships.json as the schema reference
4. Uses output_graph_rules.json for field code mappings

NODE TYPES CREATED:
- company: The primary entity being searched
- person: Officers, directors, PSCs, beneficial owners
- address: Registered addresses, business addresses

EDGE TYPES CREATED (from relationships.json):
- officer_of: Person → Company (director, secretary, etc.)
- beneficial_owner_of: Person/Company → Company (PSC, UBO)
- shareholder_of: Person/Company → Company
- registered_in: Company → Country
- has_address: Company/Person → Address
- has_email: Company → Email
- has_phone: Company → Phone
- has_website: Company → URL

Usage:
    from country_graph_adapter import CountryGraphAdapter

    adapter = CountryGraphAdapter(project_id="abc123")

    # From UK CLI
    uk_result = await uk_cli.execute("cuk: Tesco")
    ops = adapter.from_uk_result(uk_result)

    # From Norway CLI
    no_result = await no_cli.execute("cno: Equinor")
    ops = adapter.from_no_result(no_result)

    # Persist to Elasticsearch
    stats = await adapter.persist(ops)
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from enum import Enum
import hashlib

logger = logging.getLogger(__name__)

MATRIX_DIR = Path(__file__).parent

# Load sector classification
_SECTORS_CACHE = None

def _load_sectors():
    """Load NACE sector classification."""
    global _SECTORS_CACHE
    if _SECTORS_CACHE is None:
        try:
            with open(MATRIX_DIR / "sectors_nace_rev2.json") as f:
                _SECTORS_CACHE = json.load(f)
        except Exception as e:
            logger.warning(f"Could not load sectors: {e}")
            _SECTORS_CACHE = []
    return _SECTORS_CACHE


def lookup_sector(code: str) -> Optional[Dict[str, Any]]:
    """
    Look up a sector by its NACE/SIC code.

    Returns dict with: section, code, name, level
    """
    sectors = _load_sectors()
    code_normalized = code.strip().replace(" ", "")

    for sector in sectors:
        if sector.get('code') == code_normalized:
            return sector

    # Try without leading zeros
    if code_normalized.startswith('0'):
        return lookup_sector(code_normalized[1:])

    return None


def get_sector_hierarchy(code: str) -> List[Dict[str, Any]]:
    """
    Get the full hierarchy for a sector code.

    Example: "25.11" returns [Section C, Division 25, Group 25.1, Class 25.11]
    """
    sectors = _load_sectors()
    result = []

    sector = lookup_sector(code)
    if not sector:
        return result

    # Get section
    section = sector.get('section', '')
    for s in sectors:
        if s.get('section') == section and s.get('level') == 1:
            result.append(s)
            break

    # Get division (2-digit)
    if len(code) >= 2:
        div_code = code[:2]
        for s in sectors:
            if s.get('code') == div_code and s.get('level') == 2:
                result.append(s)
                break

    # Get group (3-digit with dot)
    if '.' in code and len(code) >= 4:
        group_code = code[:4]  # e.g., "25.1"
        for s in sectors:
            if s.get('code') == group_code and s.get('level') == 3:
                result.append(s)
                break

    # Add the class itself if level 4
    if sector.get('level') == 4:
        result.append(sector)

    return result


# =============================================================================
# STANDARD NODE TYPES (aligned with relationships.json)
# =============================================================================

class NodeType(Enum):
    COMPANY = "company"
    PERSON = "person"
    ADDRESS = "address"
    EMAIL = "email"
    PHONE = "phone"
    URL = "url"
    COUNTRY = "country"
    DOCUMENT = "document"
    TEMPORAL = "temporal"      # LOCATION class - static axis
    INDUSTRY = "industry"     # For sector pivoting (SIC codes)
    IDENTIFIER = "identifier" # For pivotable IDs (company numbers)


# =============================================================================
# STANDARD EDGE TYPES (from relationships.json)
# =============================================================================

class EdgeType(Enum):
    # Corporate structure
    OFFICER_OF = "officer_of"
    DIRECTOR_OF = "director_of"
    SECRETARY_OF = "secretary_of"

    # Ownership
    BENEFICIAL_OWNER_OF = "beneficial_owner_of"
    SHAREHOLDER_OF = "shareholder_of"
    OWNER_OF = "owner_of"
    SUBSIDIARY_OF = "subsidiary_of"

    # Contact info
    HAS_ADDRESS = "has_address"
    HAS_EMAIL = "has_email"
    HAS_PHONE = "has_phone"
    HAS_WEBSITE = "has_website"

    # Location
    REGISTERED_IN = "registered_in"
    HEADQUARTERED_AT = "headquartered_at"

    # Documents
    FILED_WITH = "filed_with"
    ASSOCIATED_WITH = "associated_with"

    # Temporal (LOCATION axis - static)
    INCORPORATED_IN = "incorporated_in"  # Company → Temporal (year)
    ANCHORED_TO = "anchored_to"          # Entity → Temporal coordinate

    # Identifiers
    HAS_IDENTIFIER = "has_identifier"    # Company → Identifier (reg number)

    # Industry/Sector
    OPERATES_IN = "operates_in"          # Company → Industry


# =============================================================================
# GRAPH NODE
# =============================================================================

@dataclass
class GraphNode:
    """A node in the graph."""
    node_id: str
    node_type: str
    label: str
    properties: Dict[str, Any] = field(default_factory=dict)
    jurisdiction: str = ""
    source_system: str = ""
    source_url: str = ""
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type,
            "label": self.label,
            "properties": self.properties,
            "jurisdiction": self.jurisdiction,
            "source_system": self.source_system,
            "source_url": self.source_url,
            "confidence": self.confidence,
        }


# =============================================================================
# GRAPH EDGE
# =============================================================================

@dataclass
class GraphEdge:
    """An edge in the graph."""
    edge_id: str
    edge_type: str
    source_node_id: str
    target_node_id: str
    properties: Dict[str, Any] = field(default_factory=dict)
    source_system: str = ""
    source_url: str = ""
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "edge_type": self.edge_type,
            "source_node_id": self.source_node_id,
            "target_node_id": self.target_node_id,
            "properties": self.properties,
            "source_system": self.source_system,
            "source_url": self.source_url,
            "confidence": self.confidence,
        }


# =============================================================================
# GRAPH RESULT (Nodes + Edges)
# =============================================================================

@dataclass
class GraphResult:
    """Container for nodes and edges from a country query."""
    nodes: List[GraphNode] = field(default_factory=list)
    edges: List[GraphEdge] = field(default_factory=list)
    source_system: str = ""
    jurisdiction: str = ""
    query: str = ""
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "source_system": self.source_system,
            "jurisdiction": self.jurisdiction,
            "query": self.query,
            "timestamp": self.timestamp,
            "stats": {
                "node_count": len(self.nodes),
                "edge_count": len(self.edges),
            }
        }


# =============================================================================
# COUNTRY GRAPH ADAPTER
# =============================================================================

class CountryGraphAdapter:
    """
    Converts country CLI results into standardized graph nodes and edges.

    SLOT ARCHITECTURE:
    - Each company result creates a "slot" with:
      - Primary node: company
      - Metadata slots: status, company_type, employee_count (properties ON node)
      - Pivotable slots: registration_id, incorporation_year, industry (optional nodes)

    CONFIG OPTIONS:
    - create_temporal_nodes: Create year nodes for incorporation dates (enables "2020" pivoting)
    - create_identifier_nodes: Create nodes for company registration numbers
    - create_industry_nodes: Create nodes for SIC/industry codes
    """

    def __init__(
        self,
        project_id: str = None,
        create_temporal_nodes: bool = True,     # Year nodes (2020, 2021) - LOCATION axis
        create_identifier_nodes: bool = False,  # Reg number nodes (rarely needed)
        create_industry_nodes: bool = True,     # Industry/SIC nodes - SUBJECT axis
        create_industry_hierarchy: bool = True, # Create part_of edges up NACE hierarchy
    ):
        self.project_id = project_id
        self._node_cache: Dict[str, str] = {}  # label → node_id

        # Slot configuration
        self.create_temporal_nodes = create_temporal_nodes
        self.create_identifier_nodes = create_identifier_nodes
        self.create_industry_nodes = create_industry_nodes
        self.create_industry_hierarchy = create_industry_hierarchy

    def _generate_node_id(self, node_type: str, label: str, jurisdiction: str = "") -> str:
        """Generate deterministic node ID from type + label + jurisdiction."""
        normalized = f"{node_type}:{label.lower().strip()}:{jurisdiction.lower()}"
        hash_val = hashlib.sha256(normalized.encode()).hexdigest()[:12]
        return f"{node_type}_{hash_val}"

    def _generate_edge_id(self, edge_type: str, source_id: str, target_id: str) -> str:
        """Generate deterministic edge ID."""
        normalized = f"{edge_type}:{source_id}:{target_id}"
        hash_val = hashlib.sha256(normalized.encode()).hexdigest()[:12]
        return f"edge_{hash_val}"

    def _get_or_create_node(
        self,
        node_type: str,
        label: str,
        jurisdiction: str = "",
        properties: Dict = None,
        source_system: str = "",
        source_url: str = "",
    ) -> Tuple[GraphNode, bool]:
        """Get existing node or create new one. Returns (node, is_new)."""
        cache_key = f"{node_type}:{label.lower()}:{jurisdiction}"

        if cache_key in self._node_cache:
            # Return existing node reference
            node_id = self._node_cache[cache_key]
            return GraphNode(
                node_id=node_id,
                node_type=node_type,
                label=label,
                jurisdiction=jurisdiction,
            ), False

        # Create new node
        node_id = self._generate_node_id(node_type, label, jurisdiction)
        self._node_cache[cache_key] = node_id

        return GraphNode(
            node_id=node_id,
            node_type=node_type,
            label=label,
            properties=properties or {},
            jurisdiction=jurisdiction,
            source_system=source_system,
            source_url=source_url,
        ), True

    # =========================================================================
    # UK CLI ADAPTER
    # =========================================================================

    def from_uk_result(self, uk_result) -> GraphResult:
        """
        Convert UK CLI result to graph nodes and edges.

        UK Result structure:
        - companies: List[Dict] with name, company_number, status, etc.
        - officers: List[Dict] with name, officer_role, appointed_on, etc.
        - pscs: List[Dict] with name, natures_of_control, etc.
        - documents: List[Dict] with title, type, date, etc.
        """
        self._node_cache = {}
        result = GraphResult(
            source_system="companies_house_uk",
            jurisdiction="GB",
            query=uk_result.query if hasattr(uk_result, 'query') else "",
        )

        # Get registry URL base
        ch_base = "https://find-and-update.company-information.service.gov.uk"

        # Process companies
        for company in getattr(uk_result, 'companies', []):
            company_node, is_new = self._create_uk_company_node(company, ch_base)
            if is_new:
                result.nodes.append(company_node)

            # Create country edge
            country_node, is_new_country = self._get_or_create_node(
                "country", "United Kingdom", "GB"
            )
            if is_new_country:
                result.nodes.append(country_node)

            result.edges.append(GraphEdge(
                edge_id=self._generate_edge_id("registered_in", company_node.node_id, country_node.node_id),
                edge_type="registered_in",
                source_node_id=company_node.node_id,
                target_node_id=country_node.node_id,
                properties={"registration_number": company.get('company_number', '')},
                source_system="companies_house_uk",
            ))

            # Process officers for this company
            for officer in getattr(uk_result, 'officers', []):
                officer_edges = self._create_uk_officer_edges(officer, company_node, result)
                result.edges.extend(officer_edges)

            # Process PSCs (beneficial owners)
            for psc in getattr(uk_result, 'pscs', []):
                psc_edges = self._create_uk_psc_edges(psc, company_node, result)
                result.edges.extend(psc_edges)

            # Process address
            if company.get('address'):
                address_edge = self._create_address_edge(
                    company.get('address'), company_node, "GB", "companies_house_uk", result
                )
                if address_edge:
                    result.edges.append(address_edge)

        # Process standalone persons (from puk: queries)
        for person in getattr(uk_result, 'persons', []):
            person_node, is_new = self._create_uk_person_node(person)
            if is_new:
                result.nodes.append(person_node)

            # Create edges for each role
            for role in person.get('roles', []):
                role_edges = self._create_uk_person_role_edges(person_node, role, result)
                result.edges.extend(role_edges)

        return result

    def _create_uk_company_node(self, company: Dict, ch_base: str) -> Tuple[GraphNode, bool]:
        """Create company node from UK Companies House data."""
        properties = {
            "company_number": company.get('company_number', ''),
            "status": company.get('status', ''),
            "company_type": company.get('company_type', ''),
            "date_of_creation": company.get('date_of_creation', ''),
            "sic_codes": company.get('sic_codes', []),
        }

        source_url = f"{ch_base}/company/{company.get('company_number', '')}"

        return self._get_or_create_node(
            node_type="company",
            label=company.get('name', ''),
            jurisdiction="GB",
            properties=properties,
            source_system="companies_house_uk",
            source_url=source_url,
        )

    def _create_uk_person_node(self, person: Dict) -> Tuple[GraphNode, bool]:
        """Create person node from UK data."""
        properties = {
            "date_of_birth": person.get('date_of_birth', ''),
            "nationality": person.get('nationality', ''),
            "occupation": person.get('occupation', ''),
        }

        return self._get_or_create_node(
            node_type="person",
            label=person.get('name', ''),
            jurisdiction="GB",
            properties=properties,
            source_system="companies_house_uk",
        )

    def _create_uk_officer_edges(
        self, officer: Dict, company_node: GraphNode, result: GraphResult
    ) -> List[GraphEdge]:
        """Create officer edges from UK data."""
        edges = []

        # Create person node
        person_node, is_new = self._get_or_create_node(
            node_type="person",
            label=officer.get('name', ''),
            jurisdiction="GB",
            properties={
                "nationality": officer.get('nationality', ''),
                "occupation": officer.get('occupation', ''),
            },
            source_system="companies_house_uk",
        )
        if is_new:
            result.nodes.append(person_node)

        # Determine edge type from role
        role = officer.get('officer_role', '').lower()
        if 'director' in role:
            edge_type = "director_of"
        elif 'secretary' in role:
            edge_type = "secretary_of"
        else:
            edge_type = "officer_of"

        edges.append(GraphEdge(
            edge_id=self._generate_edge_id(edge_type, person_node.node_id, company_node.node_id),
            edge_type=edge_type,
            source_node_id=person_node.node_id,
            target_node_id=company_node.node_id,
            properties={
                "position": officer.get('officer_role', ''),
                "start_date": officer.get('appointed_on', ''),
                "end_date": officer.get('resigned_on', ''),
            },
            source_system="companies_house_uk",
        ))

        return edges

    def _create_uk_psc_edges(
        self, psc: Dict, company_node: GraphNode, result: GraphResult
    ) -> List[GraphEdge]:
        """Create PSC (beneficial owner) edges from UK data."""
        edges = []

        # Determine if PSC is person or company
        kind = psc.get('kind', '')
        is_corporate = 'corporate' in kind.lower()

        psc_node, is_new = self._get_or_create_node(
            node_type="company" if is_corporate else "person",
            label=psc.get('name', ''),
            jurisdiction="GB",
            properties={
                "natures_of_control": psc.get('natures_of_control', []),
            },
            source_system="companies_house_uk",
        )
        if is_new:
            result.nodes.append(psc_node)

        edges.append(GraphEdge(
            edge_id=self._generate_edge_id("beneficial_owner_of", psc_node.node_id, company_node.node_id),
            edge_type="beneficial_owner_of",
            source_node_id=psc_node.node_id,
            target_node_id=company_node.node_id,
            properties={
                "natures_of_control": psc.get('natures_of_control', []),
                "notified_on": psc.get('notified_on', ''),
                "ceased_on": psc.get('ceased_on', ''),
            },
            source_system="companies_house_uk",
        ))

        return edges

    def _create_uk_person_role_edges(
        self, person_node: GraphNode, role: Dict, result: GraphResult
    ) -> List[GraphEdge]:
        """Create edges from person's roles."""
        edges = []

        # Create company node for the role
        company_name = role.get('company_name', '')
        company_number = role.get('company_number', '')

        if company_name:
            company_node, is_new = self._get_or_create_node(
                node_type="company",
                label=company_name,
                jurisdiction="GB",
                properties={"company_number": company_number},
                source_system="companies_house_uk",
            )
            if is_new:
                result.nodes.append(company_node)

            # Determine edge type
            role_type = role.get('role_type', '').lower()
            if 'director' in role_type:
                edge_type = "director_of"
            elif 'secretary' in role_type:
                edge_type = "secretary_of"
            else:
                edge_type = "officer_of"

            edges.append(GraphEdge(
                edge_id=self._generate_edge_id(edge_type, person_node.node_id, company_node.node_id),
                edge_type=edge_type,
                source_node_id=person_node.node_id,
                target_node_id=company_node.node_id,
                properties={
                    "position": role.get('role_type', ''),
                    "start_date": role.get('appointed_on', ''),
                    "end_date": role.get('resigned_on', ''),
                },
                source_system="companies_house_uk",
            ))

        return edges

    # =========================================================================
    # NORWAY CLI ADAPTER
    # =========================================================================

    def from_no_result(self, no_result) -> GraphResult:
        """
        Convert Norway CLI result to graph nodes and edges.

        Norway Result structure:
        - companies: List[Dict] with name, org_number, status, org_form, etc.
        - persons: List[Dict] with name, role, company_name, birth_date, etc.
        """
        self._node_cache = {}
        result = GraphResult(
            source_system="brreg_no",
            jurisdiction="NO",
            query=no_result.query if hasattr(no_result, 'query') else "",
        )

        brreg_base = "https://w2.brreg.no/enhet/sok/detalj.jsp"

        # Process companies
        for company in getattr(no_result, 'companies', []):
            company_node, is_new = self._create_no_company_node(company, brreg_base)
            if is_new:
                result.nodes.append(company_node)

            # Create country edge
            country_node, is_new_country = self._get_or_create_node(
                "country", "Norway", "NO"
            )
            if is_new_country:
                result.nodes.append(country_node)

            result.edges.append(GraphEdge(
                edge_id=self._generate_edge_id("registered_in", company_node.node_id, country_node.node_id),
                edge_type="registered_in",
                source_node_id=company_node.node_id,
                target_node_id=country_node.node_id,
                properties={"registration_number": company.get('org_number', '')},
                source_system="brreg_no",
            ))

            # Process address
            if company.get('address'):
                address_edge = self._create_address_edge(
                    company.get('address'), company_node, "NO", "brreg_no", result
                )
                if address_edge:
                    result.edges.append(address_edge)

            # TEMPORAL SLOT: Incorporation year node (enables "all 2020 companies" pivot)
            if company.get('founding_date') or company.get('registration_date'):
                date = company.get('founding_date') or company.get('registration_date')
                temporal_edge = self._create_temporal_edge(
                    date, company_node, "incorporated_in", "brreg_no", result
                )
                if temporal_edge:
                    result.edges.append(temporal_edge)

            # INDUSTRY SLOT: Sector node (enables "all tech companies" pivot)
            if company.get('industry') or company.get('industry_code'):
                industry_edge = self._create_industry_edge(
                    company.get('industry', ''),
                    company.get('industry_code', ''),
                    company_node,
                    "brreg_no",
                    result
                )
                if industry_edge:
                    result.edges.append(industry_edge)

        # Process persons (from pno: queries)
        for person in getattr(no_result, 'persons', []):
            person_node, is_new = self._create_no_person_node(person)
            if is_new:
                result.nodes.append(person_node)

            # Create edge to company
            company_name = person.get('company_name', '')
            company_org_nr = person.get('company_org_number', '')

            if company_name:
                company_node, is_new_company = self._get_or_create_node(
                    node_type="company",
                    label=company_name,
                    jurisdiction="NO",
                    properties={"org_number": company_org_nr},
                    source_system="brreg_no",
                )
                if is_new_company:
                    result.nodes.append(company_node)

                # Determine edge type from role
                role = person.get('role', '').lower()
                if 'daglig leder' in role or 'administrerende' in role:
                    edge_type = "director_of"
                elif 'styreleder' in role or 'styremedlem' in role:
                    edge_type = "officer_of"
                else:
                    edge_type = "officer_of"

                result.edges.append(GraphEdge(
                    edge_id=self._generate_edge_id(edge_type, person_node.node_id, company_node.node_id),
                    edge_type=edge_type,
                    source_node_id=person_node.node_id,
                    target_node_id=company_node.node_id,
                    properties={
                        "position": person.get('role', ''),
                        "role_code": person.get('role_code', ''),
                        "is_resigned": person.get('is_fratraadt', False),
                    },
                    source_system="brreg_no",
                ))

        return result

    def _create_no_company_node(self, company: Dict, brreg_base: str) -> Tuple[GraphNode, bool]:
        """Create company node from Norway Brreg data."""
        org_nr = company.get('org_number', '')

        properties = {
            "org_number": org_nr,
            "status": company.get('status', ''),
            "org_form": company.get('org_form', ''),
            "org_form_code": company.get('org_form_code', ''),
            "industry": company.get('industry', ''),
            "industry_code": company.get('industry_code', ''),
            "registration_date": company.get('registration_date', ''),
            "founding_date": company.get('founding_date', ''),
            "employees": company.get('employees'),
            "is_bankrupt": company.get('is_bankrupt', False),
            "is_under_liquidation": company.get('is_under_liquidation', False),
        }

        source_url = f"{brreg_base}?orgnr={org_nr}"

        return self._get_or_create_node(
            node_type="company",
            label=company.get('name', ''),
            jurisdiction="NO",
            properties=properties,
            source_system="brreg_no",
            source_url=source_url,
        )

    def _create_no_person_node(self, person: Dict) -> Tuple[GraphNode, bool]:
        """Create person node from Norway data."""
        properties = {
            "birth_date": person.get('birth_date', ''),
        }

        return self._get_or_create_node(
            node_type="person",
            label=person.get('name', ''),
            jurisdiction="NO",
            properties=properties,
            source_system="brreg_no",
        )

    # =========================================================================
    # FINLAND CLI ADAPTER
    # =========================================================================

    def from_fi_result(self, fi_result) -> GraphResult:
        """
        Convert Finland CLI result to graph nodes and edges.

        Finland Result structure:
        - companies: List[Dict] with name, business_id, status, company_form, etc.
        """
        self._node_cache = {}
        result = GraphResult(
            source_system="prh_fi",
            jurisdiction="FI",
            query=fi_result.query if hasattr(fi_result, 'query') else "",
        )

        prh_base = "https://virre.prh.fi/novus/companySearch"

        # Process companies
        for company in getattr(fi_result, 'companies', []):
            company_node, is_new = self._create_fi_company_node(company, prh_base)
            if is_new:
                result.nodes.append(company_node)

            # Create country edge
            country_node, is_new_country = self._get_or_create_node(
                "country", "Finland", "FI"
            )
            if is_new_country:
                result.nodes.append(country_node)

            result.edges.append(GraphEdge(
                edge_id=self._generate_edge_id("registered_in", company_node.node_id, country_node.node_id),
                edge_type="registered_in",
                source_node_id=company_node.node_id,
                target_node_id=country_node.node_id,
                properties={"registration_number": company.get('business_id', '')},
                source_system="prh_fi",
            ))

            # Process address
            if company.get('address'):
                address_edge = self._create_address_edge(
                    company.get('address'), company_node, "FI", "prh_fi", result
                )
                if address_edge:
                    result.edges.append(address_edge)

        return result

    def _create_fi_company_node(self, company: Dict, prh_base: str) -> Tuple[GraphNode, bool]:
        """Create company node from Finland PRH data."""
        business_id = company.get('business_id', '')

        properties = {
            "business_id": business_id,
            "eu_id": company.get('eu_id', ''),
            "status": company.get('status', ''),
            "company_form": company.get('company_form', ''),
            "industry": company.get('industry', ''),
            "industry_code": company.get('industry_code', ''),
            "trade_names": company.get('trade_names', []),
            "registration_date": company.get('registration_date', ''),
            "last_modified": company.get('last_modified', ''),
        }

        source_url = f"{prh_base}?businessId={business_id}"

        return self._get_or_create_node(
            node_type="company",
            label=company.get('name', ''),
            jurisdiction="FI",
            properties=properties,
            source_system="prh_fi",
            source_url=source_url,
        )

    # =========================================================================
    # SWITZERLAND (CH) - ZEFIX
    # =========================================================================

    def from_ch_result(self, ch_result) -> GraphResult:
        """
        Convert Switzerland CLI result to graph nodes and edges.

        Switzerland Result structure:
        - companies: List[Dict] with name, uid, status, legal_form, canton, noga_code, etc.
        """
        self._node_cache = {}
        result = GraphResult(
            source_system="zefix_ch",
            jurisdiction="CH",
            query=ch_result.query if hasattr(ch_result, 'query') else "",
        )

        # Process companies
        for company in getattr(ch_result, 'companies', []):
            company_node, is_new = self._create_ch_company_node(company)
            if is_new:
                result.nodes.append(company_node)

            # Create country edge
            country_node, is_new_country = self._get_or_create_node(
                "country", "Switzerland", "CH"
            )
            if is_new_country:
                result.nodes.append(country_node)

            result.edges.append(GraphEdge(
                edge_id=self._generate_edge_id("registered_in", company_node.node_id, country_node.node_id),
                edge_type="registered_in",
                source_node_id=company_node.node_id,
                target_node_id=country_node.node_id,
                properties={"uid": company.get('uid', ''), "canton": company.get('canton', '')},
                source_system="zefix_ch",
            ))

            # Process address
            if company.get('address'):
                address_edge = self._create_address_edge(
                    company.get('address'), company_node, "CH", "zefix_ch", result
                )
                if address_edge:
                    result.edges.append(address_edge)

            # Create temporal edge for registration date
            if company.get('registration_date'):
                temporal_edge = self._create_temporal_edge(
                    company.get('registration_date'), company_node,
                    "incorporated_in", "zefix_ch", result
                )
                if temporal_edge:
                    result.edges.append(temporal_edge)

            # Create industry edge (NOGA code is based on NACE)
            if company.get('noga_code'):
                industry_edge = self._create_industry_edge(
                    "", company.get('noga_code'), company_node, "zefix_ch", result
                )
                if industry_edge:
                    result.edges.append(industry_edge)

        return result

    def _create_ch_company_node(self, company: Dict) -> Tuple[GraphNode, bool]:
        """Create company node from Switzerland ZEFIX data."""
        uid = company.get('uid', '')

        properties = {
            "uid": uid,
            "ch_id": company.get('ch_id', ''),
            "status": company.get('status', ''),
            "legal_form": company.get('legal_form', ''),
            "canton": company.get('canton', ''),
            "purpose": company.get('purpose', ''),
            "noga_code": company.get('noga_code', ''),
            "registration_date": company.get('registration_date', ''),
            "deletion_date": company.get('deletion_date', ''),
        }

        source_url = company.get('zefix_url', '')

        return self._get_or_create_node(
            node_type="company",
            label=company.get('name', ''),
            jurisdiction="CH",
            properties=properties,
            source_system="zefix_ch",
            source_url=source_url,
        )

    # =========================================================================
    # IRELAND (IE) - CRO
    # =========================================================================

    def from_ie_result(self, ie_result) -> GraphResult:
        """
        Convert Ireland CLI result to graph nodes and edges.

        Ireland Result structure:
        - companies: List[Dict] with name, company_number, status, company_type, etc.
        """
        self._node_cache = {}
        result = GraphResult(
            source_system="cro_ie",
            jurisdiction="IE",
            query=ie_result.query if hasattr(ie_result, 'query') else "",
        )

        # Process companies
        for company in getattr(ie_result, 'companies', []):
            company_node, is_new = self._create_ie_company_node(company)
            if is_new:
                result.nodes.append(company_node)

            # Create country edge
            country_node, is_new_country = self._get_or_create_node(
                "country", "Ireland", "IE"
            )
            if is_new_country:
                result.nodes.append(country_node)

            result.edges.append(GraphEdge(
                edge_id=self._generate_edge_id("registered_in", company_node.node_id, country_node.node_id),
                edge_type="registered_in",
                source_node_id=company_node.node_id,
                target_node_id=country_node.node_id,
                properties={"company_number": company.get('company_number', '')},
                source_system="cro_ie",
            ))

            # Process address
            if company.get('address'):
                address_edge = self._create_address_edge(
                    company.get('address'), company_node, "IE", "cro_ie", result
                )
                if address_edge:
                    result.edges.append(address_edge)

            # Create temporal edge for registration date
            if company.get('registration_date'):
                temporal_edge = self._create_temporal_edge(
                    company.get('registration_date'), company_node,
                    "incorporated_in", "cro_ie", result
                )
                if temporal_edge:
                    result.edges.append(temporal_edge)

        return result

    def _create_ie_company_node(self, company: Dict) -> Tuple[GraphNode, bool]:
        """Create company node from Ireland CRO data."""
        company_number = company.get('company_number', '')

        properties = {
            "company_number": company_number,
            "status": company.get('status', ''),
            "status_code": company.get('status_code', ''),
            "company_type": company.get('company_type', ''),
            "company_type_code": company.get('company_type_code', ''),
            "registration_date": company.get('registration_date', ''),
            "incorporation_year": company.get('incorporation_year'),
            "last_annual_return": company.get('last_annual_return', ''),
            "last_accounts": company.get('last_accounts', ''),
        }

        source_url = company.get('cro_url', '')

        return self._get_or_create_node(
            node_type="company",
            label=company.get('name', ''),
            jurisdiction="IE",
            properties=properties,
            source_system="cro_ie",
            source_url=source_url,
        )

    # =========================================================================
    # BELGIUM (BE) - KBO/BCE
    # =========================================================================

    def from_be_result(self, be_result) -> GraphResult:
        """
        Convert Belgium CLI result to graph nodes and edges.

        Belgium Result structure:
        - companies: List[Dict] with name, enterprise_number, status, legal_form,
          capital, nace_codes, directors, ownership_data, documents
        """
        self._node_cache = {}
        result = GraphResult(
            source_system="kbo_bce_be",
            jurisdiction="BE",
            query=be_result.query if hasattr(be_result, 'query') else "",
        )

        kbo_base = "https://kbopub.economie.fgov.be/kbopub/zoeknummerform.html"

        # Process companies
        for company in getattr(be_result, 'companies', []):
            company_node, is_new = self._create_be_company_node(company, kbo_base)
            if is_new:
                result.nodes.append(company_node)

            # Create country edge
            country_node, is_new_country = self._get_or_create_node(
                "country", "Belgium", "BE"
            )
            if is_new_country:
                result.nodes.append(country_node)

            result.edges.append(GraphEdge(
                edge_id=self._generate_edge_id("registered_in", company_node.node_id, country_node.node_id),
                edge_type="registered_in",
                source_node_id=company_node.node_id,
                target_node_id=country_node.node_id,
                properties={"enterprise_number": company.get('enterprise_number', '')},
                source_system="kbo_bce_be",
            ))

            # Process address
            if company.get('address'):
                address_edge = self._create_address_edge(
                    company.get('address'), company_node, "BE", "kbo_bce_be", result
                )
                if address_edge:
                    result.edges.append(address_edge)

            # Create temporal edge for founding date
            if company.get('founded'):
                temporal_edge = self._create_temporal_edge(
                    company.get('founded'), company_node,
                    "incorporated_in", "kbo_bce_be", result
                )
                if temporal_edge:
                    result.edges.append(temporal_edge)

            # Process directors/officers
            for director in company.get('directors', []):
                director_edges = self._create_be_director_edges(director, company_node, result)
                result.edges.extend(director_edges)

            # Process ownership data (from AI extraction)
            ownership = company.get('ownership_data', {})
            if ownership:
                # Process shareholders
                for shareholder in ownership.get('shareholders', []):
                    sh_edges = self._create_be_shareholder_edges(shareholder, company_node, result)
                    result.edges.extend(sh_edges)

                # Process beneficial owners
                for bo in ownership.get('beneficial_owners', []):
                    bo_edges = self._create_be_beneficial_owner_edges(bo, company_node, result)
                    result.edges.extend(bo_edges)

            # Create industry edges from NACE codes
            for nace in company.get('nace_codes', []):
                industry_edge = self._create_industry_edge(
                    nace.get('description', ''),
                    nace.get('code', ''),
                    company_node,
                    "kbo_bce_be",
                    result
                )
                if industry_edge:
                    result.edges.append(industry_edge)

        return result

    def _create_be_company_node(self, company: Dict, kbo_base: str) -> Tuple[GraphNode, bool]:
        """Create company node from Belgium KBO/BCE data."""
        ent_nr = company.get('enterprise_number', '')

        properties = {
            "enterprise_number": ent_nr,
            "status": company.get('status', ''),
            "legal_form": company.get('legal_form', ''),
            "capital": company.get('capital', ''),
            "founded": company.get('founded', ''),
            "nace_codes": [n.get('code') for n in company.get('nace_codes', [])],
            "document_count": company.get('document_count', 0),
        }

        source_url = f"{kbo_base}?nummer={ent_nr}"

        return self._get_or_create_node(
            node_type="company",
            label=company.get('name', ''),
            jurisdiction="BE",
            properties=properties,
            source_system="kbo_bce_be",
            source_url=source_url,
        )

    def _create_be_director_edges(
        self, director: Dict, company_node: GraphNode, result: GraphResult
    ) -> List[GraphEdge]:
        """Create director edges from Belgium KBO/BCE data."""
        edges = []

        name = director.get('name', '')
        if not name:
            return edges

        person_node, is_new = self._get_or_create_node(
            node_type="person",
            label=name,
            jurisdiction="BE",
            properties={},
            source_system="kbo_bce_be",
        )
        if is_new:
            result.nodes.append(person_node)

        # Map Belgian role to edge type
        role = director.get('role', '').lower()
        if 'director' in role or 'bestuurder' in role or 'administrateur' in role:
            edge_type = "director_of"
        elif 'gedelegeerd' in role or 'dagelijks' in role:
            edge_type = "officer_of"
        else:
            edge_type = "officer_of"

        edges.append(GraphEdge(
            edge_id=self._generate_edge_id(edge_type, person_node.node_id, company_node.node_id),
            edge_type=edge_type,
            source_node_id=person_node.node_id,
            target_node_id=company_node.node_id,
            properties={
                "position": director.get('role', ''),
                "start_date": director.get('since', ''),
            },
            source_system="kbo_bce_be",
        ))

        return edges

    def _create_be_shareholder_edges(
        self, shareholder: Dict, company_node: GraphNode, result: GraphResult
    ) -> List[GraphEdge]:
        """Create shareholder edges from AI-extracted ownership data."""
        edges = []

        name = shareholder.get('name', '')
        if not name:
            return edges

        # Determine if shareholder is person or company
        is_corporate = shareholder.get('is_corporate', False)

        sh_node, is_new = self._get_or_create_node(
            node_type="company" if is_corporate else "person",
            label=name,
            jurisdiction="BE",
            properties={
                "percentage": shareholder.get('percentage', ''),
                "share_class": shareholder.get('share_class', ''),
            },
            source_system="kbo_bce_staatsblad",
        )
        if is_new:
            result.nodes.append(sh_node)

        edges.append(GraphEdge(
            edge_id=self._generate_edge_id("shareholder_of", sh_node.node_id, company_node.node_id),
            edge_type="shareholder_of",
            source_node_id=sh_node.node_id,
            target_node_id=company_node.node_id,
            properties={
                "percentage": shareholder.get('percentage', ''),
                "share_class": shareholder.get('share_class', ''),
                "source": "staatsblad_ai_extraction",
            },
            source_system="kbo_bce_staatsblad",
        ))

        return edges

    def _create_be_beneficial_owner_edges(
        self, bo: Dict, company_node: GraphNode, result: GraphResult
    ) -> List[GraphEdge]:
        """Create beneficial owner edges from AI-extracted ownership data."""
        edges = []

        name = bo.get('name', '')
        if not name:
            return edges

        is_corporate = bo.get('is_corporate', False)

        bo_node, is_new = self._get_or_create_node(
            node_type="company" if is_corporate else "person",
            label=name,
            jurisdiction="BE",
            properties={
                "control_type": bo.get('control_type', ''),
            },
            source_system="kbo_bce_staatsblad",
        )
        if is_new:
            result.nodes.append(bo_node)

        edges.append(GraphEdge(
            edge_id=self._generate_edge_id("beneficial_owner_of", bo_node.node_id, company_node.node_id),
            edge_type="beneficial_owner_of",
            source_node_id=bo_node.node_id,
            target_node_id=company_node.node_id,
            properties={
                "control_type": bo.get('control_type', ''),
                "source": "staatsblad_ai_extraction",
            },
            source_system="kbo_bce_staatsblad",
        ))

        return edges

    # =========================================================================
    # CZECH REPUBLIC (CZ) - ARES
    # =========================================================================

    def from_cz_result(self, cz_result) -> GraphResult:
        """
        Convert Czech Republic CLI result to graph nodes and edges.

        Czech Result structure:
        - companies: List[Dict] with name, ico, status, legal_form, address, nace_code, etc.
        """
        self._node_cache = {}
        result = GraphResult(
            source_system="ares_cz",
            jurisdiction="CZ",
            query=cz_result.query if hasattr(cz_result, 'query') else "",
        )

        ares_base = "https://ares.gov.cz/ekonomicke-subjekty"

        # Process companies
        for company in getattr(cz_result, 'companies', []):
            company_node, is_new = self._create_cz_company_node(company, ares_base)
            if is_new:
                result.nodes.append(company_node)

            # Create country edge
            country_node, is_new_country = self._get_or_create_node(
                "country", "Czech Republic", "CZ"
            )
            if is_new_country:
                result.nodes.append(country_node)

            result.edges.append(GraphEdge(
                edge_id=self._generate_edge_id("registered_in", company_node.node_id, country_node.node_id),
                edge_type="registered_in",
                source_node_id=company_node.node_id,
                target_node_id=country_node.node_id,
                properties={"ico": company.get('ico', '')},
                source_system="ares_cz",
            ))

            # Process address
            if company.get('address'):
                address_edge = self._create_address_edge(
                    company.get('address'), company_node, "CZ", "ares_cz", result
                )
                if address_edge:
                    result.edges.append(address_edge)

            # Create temporal edge for founding date
            if company.get('date_founded'):
                temporal_edge = self._create_temporal_edge(
                    company.get('date_founded'), company_node,
                    "incorporated_in", "ares_cz", result
                )
                if temporal_edge:
                    result.edges.append(temporal_edge)

            # Create industry edge from NACE code
            if company.get('nace_code'):
                industry_edge = self._create_industry_edge(
                    '',
                    company.get('nace_code'),
                    company_node,
                    "ares_cz",
                    result
                )
                if industry_edge:
                    result.edges.append(industry_edge)

        return result

    def _create_cz_company_node(self, company: Dict, ares_base: str) -> Tuple[GraphNode, bool]:
        """Create company node from Czech ARES data."""
        ico = company.get('ico', '')

        properties = {
            "ico": ico,
            "dic": company.get('dic', ''),
            "status": company.get('status', ''),
            "legal_form": company.get('legal_form', ''),
            "city": company.get('city', ''),
            "postal_code": company.get('postal_code', ''),
            "date_founded": company.get('date_founded', ''),
            "date_dissolved": company.get('date_dissolved', ''),
            "nace_code": company.get('nace_code', ''),
        }

        source_url = f"{ares_base}?ico={ico}"

        return self._get_or_create_node(
            node_type="company",
            label=company.get('name', ''),
            jurisdiction="CZ",
            properties=properties,
            source_system="ares_cz",
            source_url=source_url,
        )

    # =========================================================================
    # GLEIF ADAPTER (Global LEI System)
    # =========================================================================

    def from_gleif_result(self, gleif_result) -> GraphResult:
        """
        Convert GLEIF CLI result to graph nodes and edges.

        GLEIF provides GLOBAL company data via Legal Entity Identifiers (LEI).
        Unlike country-specific registries, GLEIF covers ALL jurisdictions.

        GLEIF Result structure:
        - companies: List[Dict] with lei, legal_name, previous_names, jurisdiction,
          legal_form, status, creation_date, registration_status, addresses,
          has_parent, has_ultimate_parent, has_subsidiaries, relationships

        Special features:
        - LEI: 20-character unique global identifier
        - Parent/subsidiary relationships across jurisdictions
        - BIC/SWIFT codes for financial institutions
        """
        self._node_cache = {}
        result = GraphResult(
            source_system="gleif",
            jurisdiction="GLOBAL",  # GLEIF is jurisdiction-agnostic
            query=gleif_result.query if hasattr(gleif_result, 'query') else "",
        )

        gleif_base = "https://search.gleif.org/#/record"

        # Process companies
        for company in getattr(gleif_result, 'companies', []):
            company_node, is_new = self._create_gleif_company_node(company, gleif_base)
            if is_new:
                result.nodes.append(company_node)

            # Get jurisdiction from company data
            jurisdiction = company.get('jurisdiction', '')

            # Create country edge if jurisdiction is known
            if jurisdiction:
                country_name = self._jurisdiction_to_country_name(jurisdiction)
                country_node, is_new_country = self._get_or_create_node(
                    "country", country_name, jurisdiction
                )
                if is_new_country:
                    result.nodes.append(country_node)

                result.edges.append(GraphEdge(
                    edge_id=self._generate_edge_id("registered_in", company_node.node_id, country_node.node_id),
                    edge_type="registered_in",
                    source_node_id=company_node.node_id,
                    target_node_id=country_node.node_id,
                    properties={
                        "lei": company.get('lei', ''),
                        "registered_as": company.get('registered_as', ''),
                    },
                    source_system="gleif",
                ))

            # Process legal address
            legal_addr = company.get('legal_address', {})
            if legal_addr and legal_addr.get('city'):
                address_str = self._format_gleif_address(legal_addr)
                if address_str:
                    address_edge = self._create_address_edge(
                        address_str, company_node, jurisdiction, "gleif", result
                    )
                    if address_edge:
                        result.edges.append(address_edge)

            # Process headquarters address (if different)
            hq_addr = company.get('headquarters_address', {})
            if hq_addr and hq_addr.get('city') and hq_addr != legal_addr:
                hq_str = self._format_gleif_address(hq_addr)
                if hq_str:
                    hq_node, is_new_hq = self._get_or_create_node(
                        node_type="address",
                        label=hq_str,
                        jurisdiction=hq_addr.get('country', ''),
                        source_system="gleif",
                    )
                    if is_new_hq:
                        result.nodes.append(hq_node)

                    result.edges.append(GraphEdge(
                        edge_id=self._generate_edge_id("headquartered_at", company_node.node_id, hq_node.node_id),
                        edge_type="headquartered_at",
                        source_node_id=company_node.node_id,
                        target_node_id=hq_node.node_id,
                        properties={"address_type": "headquarters"},
                        source_system="gleif",
                    ))

            # Create temporal edge for creation date
            if company.get('creation_date'):
                temporal_edge = self._create_temporal_edge(
                    company.get('creation_date'), company_node,
                    "incorporated_in", "gleif", result
                )
                if temporal_edge:
                    result.edges.append(temporal_edge)

            # Process parent/subsidiary relationships from raw relationships data
            relationships = company.get('relationships', {})

            # Direct parent
            direct_parent = relationships.get('direct-parent', {})
            if direct_parent and direct_parent.get('links', {}).get('lei-record'):
                parent_url = direct_parent['links']['lei-record']
                # Extract parent LEI from URL (format: /api/v1/lei-records/{LEI})
                parent_lei = parent_url.split('/')[-1] if parent_url else None
                if parent_lei:
                    parent_node, is_new_parent = self._get_or_create_node(
                        node_type="company",
                        label=f"LEI:{parent_lei}",  # Placeholder until enriched
                        jurisdiction="",
                        properties={"lei": parent_lei, "relationship": "direct_parent"},
                        source_system="gleif",
                    )
                    if is_new_parent:
                        result.nodes.append(parent_node)

                    result.edges.append(GraphEdge(
                        edge_id=self._generate_edge_id("subsidiary_of", company_node.node_id, parent_node.node_id),
                        edge_type="subsidiary_of",
                        source_node_id=company_node.node_id,
                        target_node_id=parent_node.node_id,
                        properties={"relationship_type": "direct_parent"},
                        source_system="gleif",
                    ))

            # Ultimate parent (if different from direct parent)
            ultimate_parent = relationships.get('ultimate-parent', {})
            if ultimate_parent and ultimate_parent.get('links', {}).get('lei-record'):
                ult_parent_url = ultimate_parent['links']['lei-record']
                ult_parent_lei = ult_parent_url.split('/')[-1] if ult_parent_url else None
                # Only create if different from direct parent
                if ult_parent_lei and ult_parent_lei != parent_lei:
                    ult_node, is_new_ult = self._get_or_create_node(
                        node_type="company",
                        label=f"LEI:{ult_parent_lei}",
                        jurisdiction="",
                        properties={"lei": ult_parent_lei, "relationship": "ultimate_parent"},
                        source_system="gleif",
                    )
                    if is_new_ult:
                        result.nodes.append(ult_node)

                    result.edges.append(GraphEdge(
                        edge_id=self._generate_edge_id("subsidiary_of", company_node.node_id, ult_node.node_id),
                        edge_type="subsidiary_of",
                        source_node_id=company_node.node_id,
                        target_node_id=ult_node.node_id,
                        properties={"relationship_type": "ultimate_parent"},
                        source_system="gleif",
                    ))

            # Process subsidiaries if available (from --include-children flag)
            for subsidiary in company.get('subsidiaries', []):
                sub_name = subsidiary.get('name', '')
                sub_lei = subsidiary.get('lei', '')
                if sub_name or sub_lei:
                    sub_node, is_new_sub = self._get_or_create_node(
                        node_type="company",
                        label=sub_name or f"LEI:{sub_lei}",
                        jurisdiction=subsidiary.get('jurisdiction', ''),
                        properties={
                            "lei": sub_lei,
                            "status": subsidiary.get('status', ''),
                        },
                        source_system="gleif",
                    )
                    if is_new_sub:
                        result.nodes.append(sub_node)

                    result.edges.append(GraphEdge(
                        edge_id=self._generate_edge_id("subsidiary_of", sub_node.node_id, company_node.node_id),
                        edge_type="subsidiary_of",
                        source_node_id=sub_node.node_id,
                        target_node_id=company_node.node_id,
                        properties={"relationship_type": "direct_subsidiary"},
                        source_system="gleif",
                    ))

        return result

    def _create_gleif_company_node(self, company: Dict, gleif_base: str) -> Tuple[GraphNode, bool]:
        """Create company node from GLEIF LEI data."""
        lei = company.get('lei', '')

        properties = {
            "lei": lei,
            "status": company.get('status', ''),
            "registration_status": company.get('registration_status', ''),
            "legal_form": company.get('legal_form', ''),
            "creation_date": company.get('creation_date', ''),
            "initial_registration": company.get('initial_registration', ''),
            "last_update": company.get('last_update', ''),
            "next_renewal": company.get('next_renewal', ''),
            "managing_lou": company.get('managing_lou', ''),
            "registered_at": company.get('registered_at', ''),
            "registered_as": company.get('registered_as', ''),
            "previous_names": company.get('previous_names', []),
            "bic": company.get('bic', []) if isinstance(company.get('bic'), list) else [company.get('bic')] if company.get('bic') else [],
            "ocid": company.get('ocid', ''),
            "has_parent": company.get('has_parent', False),
            "has_ultimate_parent": company.get('has_ultimate_parent', False),
            "has_subsidiaries": company.get('has_subsidiaries', False),
        }

        source_url = f"{gleif_base}/{lei}" if lei else ""

        return self._get_or_create_node(
            node_type="company",
            label=company.get('legal_name', ''),
            jurisdiction=company.get('jurisdiction', ''),
            properties=properties,
            source_system="gleif",
            source_url=source_url,
        )

    def _format_gleif_address(self, addr: Dict) -> str:
        """Format GLEIF address dict into string."""
        parts = []
        lines = addr.get('lines', [])
        if lines:
            parts.extend(lines)
        if addr.get('city'):
            parts.append(addr.get('city'))
        if addr.get('region'):
            parts.append(addr.get('region'))
        if addr.get('postal_code'):
            parts.append(addr.get('postal_code'))
        if addr.get('country'):
            parts.append(addr.get('country'))
        return ', '.join(filter(None, parts))

    def _jurisdiction_to_country_name(self, code: str) -> str:
        """Map jurisdiction code to country name."""
        country_map = {
            'US': 'United States', 'GB': 'United Kingdom', 'UK': 'United Kingdom',
            'DE': 'Germany', 'FR': 'France', 'NL': 'Netherlands',
            'BE': 'Belgium', 'LU': 'Luxembourg', 'CH': 'Switzerland',
            'NO': 'Norway', 'SE': 'Sweden', 'DK': 'Denmark', 'FI': 'Finland',
            'IE': 'Ireland', 'IT': 'Italy', 'ES': 'Spain', 'PT': 'Portugal',
            'AT': 'Austria', 'CZ': 'Czech Republic', 'PL': 'Poland',
            'HU': 'Hungary', 'HR': 'Croatia', 'RU': 'Russia',
            'JP': 'Japan', 'CN': 'China', 'HK': 'Hong Kong', 'SG': 'Singapore',
            'AU': 'Australia', 'NZ': 'New Zealand', 'CA': 'Canada',
            'BR': 'Brazil', 'MX': 'Mexico', 'ZA': 'South Africa',
            'AE': 'United Arab Emirates', 'SA': 'Saudi Arabia',
            'IN': 'India', 'KR': 'South Korea', 'TW': 'Taiwan',
        }
        # Handle compound codes like "US-DE" (Delaware, US) or "GB-EAW" (England & Wales)
        base_code = code.split('-')[0] if '-' in code else code
        return country_map.get(base_code.upper(), base_code)

    # =========================================================================
    # COMMON HELPERS
    # =========================================================================

    def _create_address_edge(
        self,
        address: str,
        entity_node: GraphNode,
        jurisdiction: str,
        source_system: str,
        result: GraphResult,
    ) -> Optional[GraphEdge]:
        """Create address node and has_address edge."""
        if not address or not address.strip():
            return None

        address_node, is_new = self._get_or_create_node(
            node_type="address",
            label=address,
            jurisdiction=jurisdiction,
            source_system=source_system,
        )
        if is_new:
            result.nodes.append(address_node)

        return GraphEdge(
            edge_id=self._generate_edge_id("has_address", entity_node.node_id, address_node.node_id),
            edge_type="has_address",
            source_node_id=entity_node.node_id,
            target_node_id=address_node.node_id,
            properties={"address_type": "registered"},
            source_system=source_system,
        )

    def _create_temporal_edge(
        self,
        date_str: str,
        entity_node: GraphNode,
        edge_type: str,
        source_system: str,
        result: GraphResult,
    ) -> Optional[GraphEdge]:
        """
        Create temporal node (year) and edge to entity.

        This enables temporal pivoting: "Show all companies incorporated in 2020"

        LOCATION AXIS (Static): Years don't change - 2020 is always 2020.
        """
        if not self.create_temporal_nodes or not date_str:
            return None

        # Extract year from date string (handles "2020-01-15", "2020", etc.)
        year = None
        if isinstance(date_str, str):
            import re
            match = re.search(r'(\d{4})', date_str)
            if match:
                year = match.group(1)

        if not year:
            return None

        # Create year node
        year_node, is_new = self._get_or_create_node(
            node_type="temporal",
            label=year,
            jurisdiction="",  # Temporal is jurisdiction-agnostic
            properties={"temporal_type": "year", "value": int(year)},
            source_system=source_system,
        )
        if is_new:
            result.nodes.append(year_node)

        return GraphEdge(
            edge_id=self._generate_edge_id(edge_type, entity_node.node_id, year_node.node_id),
            edge_type=edge_type,
            source_node_id=entity_node.node_id,
            target_node_id=year_node.node_id,
            properties={"full_date": date_str},
            source_system=source_system,
        )

    def _create_industry_edge(
        self,
        industry: str,
        industry_code: str,
        entity_node: GraphNode,
        source_system: str,
        result: GraphResult,
    ) -> Optional[GraphEdge]:
        """
        Create industry node(s) and operates_in edge.

        Uses codified NACE sector classification.
        Creates hierarchy: Company → Class → Group → Division → Section

        SUBJECT AXIS: Industries are dynamic (companies move between them).
        """
        if not self.create_industry_nodes or (not industry and not industry_code):
            return None

        # Normalize code (handle Norwegian codes like "06.100" → "06.10")
        code = industry_code.strip() if industry_code else ""
        if code and len(code) > 5 and code.count('.') == 1:
            # Norwegian codes have extra digit: "06.100" → "06.10"
            code = code[:5]

        # Look up in codified NACE classification
        sector_info = lookup_sector(code) if code else None

        if sector_info:
            # Use official NACE name
            label = sector_info.get('code', code)
            name = sector_info.get('name', industry)
            level = sector_info.get('level', 4)
            section = sector_info.get('section', '')
        else:
            # Fallback for unknown codes
            label = code if code else industry[:50] if industry else "Unknown"
            name = industry
            level = 4
            section = ""

        # Create the primary industry node (the specific class)
        industry_node, is_new = self._get_or_create_node(
            node_type="industry",
            label=label,
            jurisdiction="",  # Industries are global concepts (SUBJECT axis)
            properties={
                "code": code,
                "name": name,
                "level": level,
                "section": section,
                "classification": "NACE_REV2",
            },
            source_system=source_system,
        )
        if is_new:
            result.nodes.append(industry_node)

        # Create operates_in edge from company to industry
        edge = GraphEdge(
            edge_id=self._generate_edge_id("operates_in", entity_node.node_id, industry_node.node_id),
            edge_type="operates_in",
            source_node_id=entity_node.node_id,
            target_node_id=industry_node.node_id,
            properties={"primary": True, "raw_code": industry_code, "raw_description": industry},
            source_system=source_system,
        )

        # Optionally create hierarchy edges (class → group → division → section)
        if code and self.create_industry_hierarchy:
            hierarchy = get_sector_hierarchy(code)
            prev_node = industry_node
            for ancestor in reversed(hierarchy[:-1]):  # Skip the class itself
                ancestor_node, is_new_ancestor = self._get_or_create_node(
                    node_type="industry",
                    label=ancestor.get('code', '') or ancestor.get('section', ''),
                    jurisdiction="",
                    properties={
                        "code": ancestor.get('code', ''),
                        "name": ancestor.get('name', ''),
                        "level": ancestor.get('level', 1),
                        "section": ancestor.get('section', ''),
                        "classification": "NACE_REV2",
                    },
                    source_system="nace_classification",
                )
                if is_new_ancestor:
                    result.nodes.append(ancestor_node)

                # Create part_of edge
                part_of_edge = GraphEdge(
                    edge_id=self._generate_edge_id("part_of", prev_node.node_id, ancestor_node.node_id),
                    edge_type="part_of",
                    source_node_id=prev_node.node_id,
                    target_node_id=ancestor_node.node_id,
                    properties={},
                    source_system="nace_classification",
                )
                result.edges.append(part_of_edge)
                prev_node = ancestor_node

        return edge

    def _create_identifier_edge(
        self,
        identifier: str,
        identifier_type: str,
        entity_node: GraphNode,
        jurisdiction: str,
        source_system: str,
        result: GraphResult,
    ) -> Optional[GraphEdge]:
        """
        Create identifier node and has_identifier edge.

        Only useful when you need to pivot FROM the identifier:
        "Find all entities with ID 12345678" (rarely needed)

        Usually, identifier should just be metadata on the entity.
        """
        if not self.create_identifier_nodes or not identifier:
            return None

        id_node, is_new = self._get_or_create_node(
            node_type="identifier",
            label=identifier,
            jurisdiction=jurisdiction,
            properties={"id_type": identifier_type},
            source_system=source_system,
        )
        if is_new:
            result.nodes.append(id_node)

        return GraphEdge(
            edge_id=self._generate_edge_id("has_identifier", entity_node.node_id, id_node.node_id),
            edge_type="has_identifier",
            source_node_id=entity_node.node_id,
            target_node_id=id_node.node_id,
            properties={"id_type": identifier_type},
            source_system=source_system,
        )

    def from_us_result(self, us_result, jurisdiction: str) -> GraphResult:
        """Convert US result to graph nodes/edges."""
        try:
            from country_engines.US.us_output import USOutput
        except ImportError as exc:
            logger.warning(f"US output module not available: {exc}")
            return GraphResult(jurisdiction=jurisdiction, source_system="US")

        output = USOutput()
        return output.to_graph(us_result, jurisdiction)

    # =========================================================================
    # GENERIC DISPATCHER
    # =========================================================================

    def from_result(self, result, jurisdiction: str) -> GraphResult:
        """
        Dispatch to appropriate adapter based on jurisdiction.

        Args:
            result: Country CLI result object
            jurisdiction: ISO country code (GB, NO, FI)

        Returns:
            GraphResult with nodes and edges
        """
        jur_upper = jurisdiction.upper()

        if jur_upper in ('GB', 'UK'):
            return self.from_uk_result(result)
        elif jur_upper == 'NO':
            return self.from_no_result(result)
        elif jur_upper == 'FI':
            return self.from_fi_result(result)
        elif jur_upper == 'CH':
            return self.from_ch_result(result)
        elif jur_upper == 'IE':
            return self.from_ie_result(result)
        elif jur_upper == 'BE':
            return self.from_be_result(result)
        elif jur_upper == 'CZ':
            return self.from_cz_result(result)
        elif jur_upper == 'US' or jur_upper.startswith('US_'):
            return self.from_us_result(result, jur_upper)
        elif jur_upper in ('GLOBAL', 'LEI', 'GLEIF'):
            return self.from_gleif_result(result)
        else:
            logger.warning(f"No adapter for jurisdiction: {jurisdiction}")
            return GraphResult(jurisdiction=jurisdiction)

    # =========================================================================
    # PERSISTENCE TO ELASTICSEARCH
    # =========================================================================

    async def persist_to_elastic(
        self,
        graph_result: GraphResult,
        project_id: str = None,
    ) -> Dict[str, int]:
        """
        Persist graph result to Elasticsearch cymonides-1-{project_id} index.

        CYMONIDES MANDATE: Edges are EMBEDDED in nodes, not stored separately.

        Args:
            graph_result: GraphResult with nodes and edges
            project_id: Project ID for index name (required!)

        Returns:
            stats: {"nodes_created": N, "nodes_updated": N, "edges_embedded": N}
        """
        from elasticsearch import AsyncElasticsearch
        import os

        pid = project_id or self.project_id
        if not pid:
            raise ValueError("project_id is required for persistence")

        index_name = f"cymonides-1-{pid}"
        es_url = os.environ.get("ELASTICSEARCH_URL", "http://localhost:9200")

        stats = {"nodes_created": 0, "nodes_updated": 0, "edges_embedded": 0}

        es = AsyncElasticsearch([es_url])

        try:
            # Build edge lookup: source_node_id → list of edges
            edges_by_source: Dict[str, List[GraphEdge]] = {}
            for edge in graph_result.edges:
                src = edge.source_node_id
                if src not in edges_by_source:
                    edges_by_source[src] = []
                edges_by_source[src].append(edge)

            # Process each node
            for node in graph_result.nodes:
                node_id = node.node_id

                # Build embedded edges for this node
                embedded_edges = []
                for edge in edges_by_source.get(node_id, []):
                    embedded_edge = {
                        "edge_id": edge.edge_id,
                        "target_id": edge.target_node_id,
                        "target_label": self._get_node_label(edge.target_node_id, graph_result.nodes),
                        "target_class": self._get_node_class(edge.target_node_id, graph_result.nodes),
                        "target_type": self._get_node_type(edge.target_node_id, graph_result.nodes),
                        "relationship": edge.edge_type,
                        "direction": "outgoing",
                        "metadata": {
                            **edge.properties,
                            "source_system": edge.source_system,
                            "source_url": edge.source_url,
                            "created_at": datetime.utcnow().isoformat(),
                        }
                    }
                    embedded_edges.append(embedded_edge)
                    stats["edges_embedded"] += 1

                # Build node document
                doc = {
                    "id": node_id,
                    "label": node.label,
                    "canonicalValue": node.label.lower().strip(),
                    "node_class": self._map_node_type_to_class(node.node_type),
                    "type": node.node_type,
                    "jurisdiction": node.jurisdiction,
                    "content": node.label,
                    "description": f"{node.node_type.title()}: {node.label}",
                    "metadata": {
                        **node.properties,
                        "source_system": node.source_system,
                        "source_url": node.source_url,
                        "confidence": node.confidence,
                        "created_at": datetime.utcnow().isoformat(),
                    },
                    "embedded_edges": embedded_edges,
                }

                # Check if node exists
                try:
                    exists = await es.exists(index=index_name, id=node_id)
                    if exists:
                        # Update: merge embedded_edges
                        await es.update(
                            index=index_name,
                            id=node_id,
                            body={
                                "script": {
                                    "source": """
                                        if (ctx._source.embedded_edges == null) {
                                            ctx._source.embedded_edges = [];
                                        }
                                        for (newEdge in params.new_edges) {
                                            boolean exists = false;
                                            for (edge in ctx._source.embedded_edges) {
                                                if (edge.edge_id == newEdge.edge_id) {
                                                    exists = true;
                                                    break;
                                                }
                                            }
                                            if (!exists) {
                                                ctx._source.embedded_edges.add(newEdge);
                                            }
                                        }
                                        ctx._source.metadata.updated_at = params.updated_at;
                                    """,
                                    "lang": "painless",
                                    "params": {
                                        "new_edges": embedded_edges,
                                        "updated_at": datetime.utcnow().isoformat()
                                    }
                                }
                            }
                        )
                        stats["nodes_updated"] += 1
                    else:
                        # Create new node
                        await es.index(index=index_name, id=node_id, document=doc)
                        stats["nodes_created"] += 1

                except Exception as e:
                    logger.error(f"Error persisting node {node_id}: {e}")

            logger.info(f"Graph persistence to {index_name}: {stats}")

        finally:
            await es.close()

        return stats

    def _get_node_label(self, node_id: str, nodes: List[GraphNode]) -> str:
        """Get label for a node by ID."""
        for node in nodes:
            if node.node_id == node_id:
                return node.label
        return node_id

    def _get_node_class(self, node_id: str, nodes: List[GraphNode]) -> str:
        """Get node_class for a node by ID."""
        for node in nodes:
            if node.node_id == node_id:
                return self._map_node_type_to_class(node.node_type)
        return "entity"

    def _get_node_type(self, node_id: str, nodes: List[GraphNode]) -> str:
        """Get type for a node by ID."""
        for node in nodes:
            if node.node_id == node_id:
                return node.node_type
        return "unknown"

    def _map_node_type_to_class(self, node_type: str) -> str:
        """Map node type to cymonides node_class."""
        class_map = {
            "company": "entity",
            "person": "entity",
            "address": "location",
            "country": "location",
            "temporal": "location",
            "industry": "subject",
            "email": "contact",
            "phone": "contact",
            "username": "contact",
            "linkedin": "contact",
            "url": "contact",
            "domain": "contact",
            "document": "source",
        }
        return class_map.get(node_type, "entity")


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def convert_country_result(result, jurisdiction: str, project_id: str = None) -> GraphResult:
    """
    Convert a country CLI result to a GraphResult.

    Usage:
        from country_graph_adapter import convert_country_result

        uk_result = await uk_cli.execute("cuk: Tesco")
        graph = convert_country_result(uk_result, "GB")
        print(f"Nodes: {len(graph.nodes)}, Edges: {len(graph.edges)}")
    """
    adapter = CountryGraphAdapter(project_id=project_id)
    return adapter.from_result(result, jurisdiction)


# =============================================================================
# CLI FOR TESTING
# =============================================================================

if __name__ == "__main__":
    import argparse
    import asyncio
    import sys

    parser = argparse.ArgumentParser(description="Test country graph adapter")
    parser.add_argument("--test-uk", action="store_true", help="Test UK adapter")
    parser.add_argument("--test-no", action="store_true", help="Test Norway adapter")
    parser.add_argument("--test-fi", action="store_true", help="Test Finland adapter")
    args = parser.parse_args()

    async def test_uk():
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "BACKEND" / "modules"))
        from country_engines.UK.uk_unified_cli import UKUnifiedCLI

        cli = UKUnifiedCLI()
        result = await cli.execute("cuk: Tesco")

        adapter = CountryGraphAdapter(project_id="test")
        graph = adapter.from_uk_result(result)

        print(f"\n{'='*60}")
        print(f"UK GRAPH RESULT")
        print(f"{'='*60}")
        print(f"Nodes: {len(graph.nodes)}")
        for node in graph.nodes[:10]:
            print(f"  [{node.node_type}] {node.label}")
        print(f"Edges: {len(graph.edges)}")
        for edge in graph.edges[:10]:
            print(f"  {edge.source_node_id} --[{edge.edge_type}]--> {edge.target_node_id}")

    async def test_no():
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "BACKEND" / "modules"))
        from country_engines.NO.no_unified_cli import NOUnifiedCLI

        cli = NOUnifiedCLI()
        result = await cli.execute("cno: Equinor")

        adapter = CountryGraphAdapter(project_id="test")
        graph = adapter.from_no_result(result)

        print(f"\n{'='*60}")
        print(f"NORWAY GRAPH RESULT")
        print(f"{'='*60}")
        print(f"Nodes: {len(graph.nodes)}")
        for node in graph.nodes[:10]:
            print(f"  [{node.node_type}] {node.label}")
        print(f"Edges: {len(graph.edges)}")
        for edge in graph.edges[:10]:
            print(f"  {edge.source_node_id} --[{edge.edge_type}]--> {edge.target_node_id}")

    async def test_fi():
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "BACKEND" / "modules"))
        from country_engines.FI.fi_unified_cli import FIUnifiedCLI

        cli = FIUnifiedCLI()
        result = await cli.execute("cfi: Nokia")

        adapter = CountryGraphAdapter(project_id="test")
        graph = adapter.from_fi_result(result)

        print(f"\n{'='*60}")
        print(f"FINLAND GRAPH RESULT")
        print(f"{'='*60}")
        print(f"Nodes: {len(graph.nodes)}")
        for node in graph.nodes[:10]:
            print(f"  [{node.node_type}] {node.label}")
        print(f"Edges: {len(graph.edges)}")
        for edge in graph.edges[:10]:
            print(f"  {edge.source_node_id} --[{edge.edge_type}]--> {edge.target_node_id}")

    if args.test_uk:
        asyncio.run(test_uk())
    elif args.test_no:
        asyncio.run(test_no())
    elif args.test_fi:
        asyncio.run(test_fi())
    else:
        print("Use --test-uk, --test-no, or --test-fi to test adapters")
