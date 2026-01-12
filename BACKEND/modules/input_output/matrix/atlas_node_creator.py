#!/usr/bin/env python3
"""
ATLAS Node Creator - Create nodes and edges from ATLAS unified index results

This module handles the integration between ATLAS unified indices and the
cymonides-1-{projectId} graph storage. When ATLAS lookups return results,
this module:

1. Creates nodes in cymonides-1-{projectId} index
2. Creates embedded_edges based on relationships.json ontology
3. Logs to scenarios.json for audit trail
4. Handles deduplication via deterministic IDs

Node Types Created:
- company: From companies_unified
- person: From persons_unified
- email: From emails_unified
- phone: From phones_unified
- linkedin: From linkedin_unified

Edge Types Created (per relationships.json):
- works_for: person -> company
- officer_of: person -> company
- has_email: person/company -> email
- has_phone: person/company -> phone
- has_linkedin: person/company -> linkedin
- same_as: entity -> entity (for cross-references)
"""

import os
import json
import hashlib
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass, field, asdict
from elasticsearch import Elasticsearch

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Paths
MATRIX_DIR = Path(__file__).parent
ONTOLOGY_DIR = MATRIX_DIR.parent / "ontology"
PROJECT_ROOT = MATRIX_DIR.parent.parent

# Load environment
ENV_FILE = PROJECT_ROOT / ".env"
if ENV_FILE.exists():
    from dotenv import load_dotenv
    load_dotenv(ENV_FILE)


@dataclass
class EmbeddedEdge:
    """Edge embedded within a node document."""
    target_id: str
    target_class: str  # source, entity, narrative, query
    target_type: str   # person, company, email, etc.
    target_label: str
    relation: str      # works_for, has_email, etc.
    direction: str = "outgoing"  # outgoing or incoming
    confidence: float = 0.85
    metadata: Dict = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class C1Node:
    """Node for cymonides-1-{projectId} index."""
    id: str
    node_class: str = "entity"
    type: str = "company"
    label: str = ""
    canonicalValue: str = ""

    # Metadata
    metadata: Dict = field(default_factory=dict)

    # Source tracking
    sources: List[str] = field(default_factory=list)
    source_system: str = "atlas_unified"

    # Embedded edges (THE ONLY WAY TO STORE EDGES)
    embedded_edges: List[Dict] = field(default_factory=list)

    # Timestamps
    createdAt: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updatedAt: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    lastSeen: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    # Project
    projectId: Optional[str] = None

    def to_dict(self) -> Dict:
        """Convert to dict for ES indexing."""
        d = asdict(self)
        # Also set aliases for compatibility
        d['className'] = d['node_class']
        d['typeName'] = d['type']
        d['class'] = d['node_class']
        return d


class ATLASNodeCreator:
    """Create nodes and edges from ATLAS unified index results."""

    # Map ATLAS entity types to C1 node types
    TYPE_MAP = {
        'companies_unified': 'company',
        'persons_unified': 'person',
        'emails_unified': 'email',
        'phones_unified': 'phone',
        'linkedin_unified': 'linkedin',
    }

    # Relationship mappings per relationships.json
    RELATIONSHIP_MAP = {
        ('person', 'company'): 'works_for',
        ('company', 'person'): 'employs',
        ('person', 'email'): 'has_email',
        ('company', 'email'): 'has_email',
        ('person', 'phone'): 'has_phone',
        ('company', 'phone'): 'has_phone',
        ('person', 'linkedin'): 'has_linkedin',
        ('company', 'linkedin'): 'has_linkedin',
        ('company', 'company'): 'related_to',
        ('person', 'person'): 'related_to',
        # Location relationships
        ('company', 'municipality'): 'located_in',
        ('person', 'municipality'): 'located_in',
        ('company', 'country'): 'located_in',
        ('municipality', 'country'): 'part_of',
        ('municipality', 'region'): 'part_of',
        ('region', 'country'): 'part_of',
        # Industry relationships
        ('company', 'industry'): 'operates_in',
        ('person', 'industry'): 'works_in',
    }

    def __init__(self, project_id: str = None, es_host: str = None):
        self.project_id = project_id
        self.es_host = es_host or os.environ.get('ELASTICSEARCH_URL', 'http://localhost:9200')
        self.es = Elasticsearch([self.es_host])
        self.relationships = self._load_relationships()
        self.created_nodes: Dict[str, C1Node] = {}
        self.created_edges: List[EmbeddedEdge] = []

    def _load_relationships(self) -> Dict:
        """Load relationships.json ontology."""
        rel_path = ONTOLOGY_DIR / "relationships.json"
        if rel_path.exists():
            with open(rel_path) as f:
                return json.load(f)
        return {}

    def _generate_node_id(self, canonical_value: str, node_type: str) -> str:
        """Generate deterministic node ID."""
        key = f"{node_type}:{canonical_value.lower().strip()}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]

    def _get_index_name(self) -> str:
        """Get project-specific index name."""
        if self.project_id:
            return f"cymonides-1-{self.project_id}"
        return "cymonides-1-default"

    def _ensure_index(self) -> None:
        """Ensure cymonides-1-{projectId} index exists."""
        index_name = self._get_index_name()
        if not self.es.indices.exists(index=index_name):
            # Create with basic mapping
            mapping = {
                "mappings": {
                    "properties": {
                        "id": {"type": "keyword"},
                        "node_class": {"type": "keyword"},
                        "type": {"type": "keyword"},
                        "label": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                        "canonicalValue": {"type": "keyword"},
                        "sources": {"type": "keyword"},
                        "source_system": {"type": "keyword"},
                        "projectId": {"type": "keyword"},
                        "createdAt": {"type": "date"},
                        "updatedAt": {"type": "date"},
                        "lastSeen": {"type": "date"},
                        "embedded_edges": {
                            "type": "nested",
                            "properties": {
                                "target_id": {"type": "keyword"},
                                "target_class": {"type": "keyword"},
                                "target_type": {"type": "keyword"},
                                "target_label": {"type": "text"},
                                "relation": {"type": "keyword"},
                                "direction": {"type": "keyword"},
                                "confidence": {"type": "float"},
                                "created_at": {"type": "date"}
                            }
                        },
                        "metadata": {"type": "object", "enabled": True}
                    }
                },
                "settings": {
                    "number_of_shards": 1,
                    "number_of_replicas": 0
                }
            }
            self.es.indices.create(index=index_name, body=mapping)
            logger.info(f"Created index: {index_name}")

    def create_node_from_atlas(self, atlas_record: Dict, source_index: str) -> C1Node:
        """Create a C1 node from an ATLAS unified index record.

        Args:
            atlas_record: Record from ATLAS unified index
            source_index: Which unified index (companies_unified, persons_unified, etc.)

        Returns:
            C1Node ready for indexing
        """
        node_type = self.TYPE_MAP.get(source_index, 'entity')

        # Extract label and canonical value based on type
        if node_type == 'company':
            label = atlas_record.get('name') or atlas_record.get('legal_name') or 'Unknown Company'
            canonical = atlas_record.get('company_id') or label
        elif node_type == 'person':
            label = atlas_record.get('full_name') or f"{atlas_record.get('given_name', '')} {atlas_record.get('family_name', '')}".strip() or 'Unknown Person'
            canonical = atlas_record.get('person_id') or label
        elif node_type == 'email':
            label = atlas_record.get('email') or 'Unknown Email'
            canonical = atlas_record.get('email_id') or label
        elif node_type == 'phone':
            label = atlas_record.get('phone_e164') or atlas_record.get('phone_raw') or 'Unknown Phone'
            canonical = atlas_record.get('phone_id') or label
        elif node_type == 'linkedin':
            label = atlas_record.get('company_name') or atlas_record.get('person_name') or atlas_record.get('profile_slug') or 'Unknown LinkedIn'
            canonical = atlas_record.get('linkedin_id') or label
        else:
            label = str(atlas_record.get('_id', 'Unknown'))
            canonical = label

        node_id = self._generate_node_id(canonical, node_type)

        # Build metadata from ATLAS record (exclude internal fields)
        metadata = {k: v for k, v in atlas_record.items()
                   if not k.startswith('_') and k not in ['embedded_edges', 'sources']}

        node = C1Node(
            id=node_id,
            node_class='entity',
            type=node_type,
            label=label,
            canonicalValue=canonical.lower().strip(),
            metadata=metadata,
            sources=atlas_record.get('sources', [source_index]),
            source_system='atlas_unified',
            projectId=self.project_id,
        )

        self.created_nodes[node_id] = node
        return node

    def create_edge(self, from_node: C1Node, to_node: C1Node,
                    relation: str = None, metadata: Dict = None) -> EmbeddedEdge:
        """Create an embedded edge between two nodes.

        Args:
            from_node: Source node
            to_node: Target node
            relation: Relationship type (auto-detected if None)
            metadata: Optional edge metadata

        Returns:
            EmbeddedEdge added to from_node
        """
        # Auto-detect relationship if not provided
        if not relation:
            key = (from_node.type, to_node.type)
            relation = self.RELATIONSHIP_MAP.get(key, 'related_to')

        # Get confidence from relationships.json
        confidence = 0.85
        rel_config = self.relationships.get(from_node.type, {}).get('edge_types', [])
        for edge_type in rel_config:
            if edge_type.get('relationship_type') == relation:
                confidence = edge_type.get('confidence_default', 0.85)
                break

        edge = EmbeddedEdge(
            target_id=to_node.id,
            target_class=to_node.node_class,
            target_type=to_node.type,
            target_label=to_node.label,
            relation=relation,
            direction='outgoing',
            confidence=confidence,
            metadata=metadata or {},
        )

        # Add to from_node's embedded_edges
        from_node.embedded_edges.append(asdict(edge))
        self.created_edges.append(edge)

        return edge

    def process_atlas_results(self, results: List[Dict], source_index: str,
                              root_entity: Dict = None,
                              auto_create_types: List[str] = None) -> Dict[str, Any]:
        """Process ATLAS results and create nodes + edges.

        Args:
            results: List of records from ATLAS unified index
            source_index: Which unified index the results came from
            root_entity: Optional root entity to link results to
            auto_create_types: List of node types to auto-create (e.g., ['company', 'municipality', 'industry'])

        Returns:
            Summary of created nodes and edges
        """
        self._ensure_index()

        nodes_created = []
        edges_created = []
        auto_create_types = auto_create_types or []

        # Create root node if provided
        root_node = None
        if root_entity:
            root_type = root_entity.get('type', 'entity')
            root_label = root_entity.get('label', root_entity.get('value', 'Root'))
            root_canonical = root_entity.get('canonical', root_label)

            root_id = self._generate_node_id(root_canonical, root_type)
            root_node = C1Node(
                id=root_id,
                type=root_type,
                label=root_label,
                canonicalValue=root_canonical.lower().strip(),
                metadata=root_entity.get('metadata', {}),
                sources=['io_cli_query'],
                projectId=self.project_id,
            )
            self.created_nodes[root_id] = root_node
            nodes_created.append(root_node)

        # Track location and industry nodes for deduplication
        location_nodes: Dict[str, C1Node] = {}  # canonical -> node
        industry_nodes: Dict[str, C1Node] = {}  # canonical -> node

        # Process each ATLAS result
        for record in results:
            node = self.create_node_from_atlas(record, source_index)
            nodes_created.append(node)

            # Create edge from root to this node if root exists
            if root_node:
                edge = self.create_edge(root_node, node)
                edges_created.append(edge)

            # Create edges based on embedded references in ATLAS record
            self._create_cross_reference_edges(node, record)

            # Auto-create municipality nodes (from city field)
            if 'municipality' in auto_create_types:
                municipality_name = record.get('city')
                if municipality_name and municipality_name.strip():
                    municipality_key = f"municipality:{municipality_name.lower().strip()}"
                    if municipality_key not in location_nodes:
                        muni_node = self._create_location_node(
                            name=municipality_name,
                            location_type='municipality',
                            country=record.get('country'),
                            region=record.get('region')
                        )
                        location_nodes[municipality_key] = muni_node
                        nodes_created.append(muni_node)
                    else:
                        muni_node = location_nodes[municipality_key]

                    # Create edge: company -> municipality
                    edge = self.create_edge(node, muni_node, 'located_in')
                    edges_created.append(edge)

            # Auto-create industry nodes
            if 'industry' in auto_create_types:
                industry_name = record.get('industry')
                if industry_name and industry_name.strip():
                    industry_key = f"industry:{industry_name.lower().strip()}"
                    if industry_key not in industry_nodes:
                        ind_node = self._create_industry_node(
                            name=industry_name,
                            naics=record.get('naics')
                        )
                        industry_nodes[industry_key] = ind_node
                        nodes_created.append(ind_node)
                    else:
                        ind_node = industry_nodes[industry_key]

                    # Create edge: company -> industry
                    edge = self.create_edge(node, ind_node, 'operates_in')
                    edges_created.append(edge)

            # Auto-create country nodes
            if 'country' in auto_create_types:
                country_name = record.get('country')
                if country_name and country_name.strip():
                    country_key = f"country:{country_name.lower().strip()}"
                    if country_key not in location_nodes:
                        country_node = self._create_location_node(
                            name=country_name,
                            location_type='country'
                        )
                        location_nodes[country_key] = country_node
                        nodes_created.append(country_node)

        # Index all nodes
        self._index_nodes(nodes_created)

        # Log to scenarios
        self._log_scenario(source_index, len(nodes_created), len(edges_created))

        return {
            'nodes_created': len(nodes_created),
            'edges_created': len(edges_created),
            'index': self._get_index_name(),
            'node_ids': [n.id for n in nodes_created],
            'location_nodes': len(location_nodes),
            'industry_nodes': len(industry_nodes),
        }

    def _create_location_node(self, name: str, location_type: str,
                               country: str = None, region: str = None) -> C1Node:
        """Create a location node (municipality, region, country).

        Args:
            name: Location name
            location_type: 'municipality', 'region', or 'country'
            country: Parent country (for municipalities/regions)
            region: Parent region (for municipalities)

        Returns:
            C1Node for the location
        """
        canonical = f"{location_type}:{name.lower().strip()}"
        if country and location_type != 'country':
            canonical = f"{location_type}:{country.lower().strip()}:{name.lower().strip()}"

        node_id = self._generate_node_id(canonical, location_type)

        metadata = {'location_type': location_type}
        if country:
            metadata['country'] = country
        if region:
            metadata['region'] = region

        node = C1Node(
            id=node_id,
            node_class='location',  # Location class, not entity
            type=location_type,
            label=name,
            canonicalValue=canonical,
            metadata=metadata,
            sources=['atlas_unified'],
            source_system='atlas_unified',
            projectId=self.project_id,
        )

        self.created_nodes[node_id] = node
        return node

    def _create_industry_node(self, name: str, naics: str = None) -> C1Node:
        """Create an industry node.

        Args:
            name: Industry name
            naics: Optional NAICS code

        Returns:
            C1Node for the industry
        """
        canonical = f"industry:{name.lower().strip()}"
        node_id = self._generate_node_id(canonical, 'industry')

        metadata = {'industry_name': name}
        if naics:
            metadata['naics'] = naics

        node = C1Node(
            id=node_id,
            node_class='category',  # Category class for industries
            type='industry',
            label=name,
            canonicalValue=canonical,
            metadata=metadata,
            sources=['atlas_unified'],
            source_system='atlas_unified',
            projectId=self.project_id,
        )

        self.created_nodes[node_id] = node
        return node

    def _create_cross_reference_edges(self, node: C1Node, atlas_record: Dict) -> None:
        """Create edges based on cross-references in ATLAS record."""
        # Company to persons (via company_ids in person records)
        if node.type == 'person':
            company_ids = atlas_record.get('company_ids', [])
            for cid in company_ids[:10]:  # Limit to prevent explosion
                if cid in self.created_nodes:
                    company_node = self.created_nodes[cid]
                    self.create_edge(node, company_node, 'works_for')

        # Person to emails
        if node.type == 'person':
            email_ids = atlas_record.get('email_ids', [])
            for eid in email_ids[:5]:
                if eid in self.created_nodes:
                    email_node = self.created_nodes[eid]
                    self.create_edge(node, email_node, 'has_email')

        # Use embedded_edges from ATLAS if present
        atlas_edges = atlas_record.get('embedded_edges', [])
        for edge_data in atlas_edges[:20]:
            target_id = edge_data.get('target_id')
            if target_id and target_id in self.created_nodes:
                target_node = self.created_nodes[target_id]
                relation = edge_data.get('relation', 'related_to')
                self.create_edge(node, target_node, relation, edge_data.get('metadata'))

    def _index_nodes(self, nodes: List[C1Node]) -> None:
        """Bulk index nodes to Elasticsearch."""
        if not nodes:
            return

        index_name = self._get_index_name()

        actions = []
        for node in nodes:
            actions.append({
                "_index": index_name,
                "_id": node.id,
                "_source": node.to_dict()
            })

        if actions:
            from elasticsearch.helpers import bulk
            success, errors = bulk(self.es, actions, raise_on_error=False)
            logger.info(f"Indexed {success} nodes to {index_name}")
            if errors:
                logger.warning(f"Indexing errors: {len(errors)}")

    def _log_scenario(self, source_index: str, nodes: int, edges: int) -> None:
        """Log to scenarios.json for audit trail."""
        scenarios_path = Path(__file__).parent.parent.parent / "server" / "services" / "cymonides" / "scenarios.json"

        if not scenarios_path.exists():
            return

        try:
            with open(scenarios_path) as f:
                scenarios = json.load(f)

            # Update summary
            scenarios['summary']['totalNodeScenarios'] = scenarios['summary'].get('totalNodeScenarios', 0) + 1
            scenarios['summary']['ioCliScenarios'] = scenarios['summary'].get('ioCliScenarios', 0) + 1

            # Check if ATLAS scenario already exists
            atlas_scenario_id = f"atlas-{source_index}"
            existing = next((s for s in scenarios.get('nodeCreationScenarios', [])
                           if s.get('id') == atlas_scenario_id), None)

            if not existing:
                # Add new scenario
                new_scenario = {
                    "id": atlas_scenario_id,
                    "description": f"Create entity nodes from ATLAS {source_index}",
                    "trigger": "IO CLI execution with ATLAS_* rules",
                    "method": "deterministic",
                    "file": "input_output/matrix/atlas_node_creator.py",
                    "function": "process_atlas_results",
                    "nodeTypes": [self.TYPE_MAP.get(source_index, 'entity')],
                    "aiModel": None,
                    "confidence": "0.85",
                    "source_system": "atlas_unified",
                    "added_at": datetime.utcnow().isoformat()
                }
                scenarios.setdefault('nodeCreationScenarios', []).append(new_scenario)

                with open(scenarios_path, 'w') as f:
                    json.dump(scenarios, f, indent=2)

                logger.info(f"Added ATLAS scenario: {atlas_scenario_id}")

        except Exception as e:
            logger.warning(f"Could not update scenarios.json: {e}")


# Convenience function for IO CLI integration
async def create_nodes_from_atlas_results(
    results: List[Dict],
    source_index: str,
    project_id: str = None,
    root_entity: Dict = None,
    auto_create_types: List[str] = None
) -> Dict[str, Any]:
    """Create nodes and edges from ATLAS lookup results.

    Called by IO CLI after ATLAS rules execute.

    Args:
        results: List of records from ATLAS unified index
        source_index: Which unified index (companies_unified, persons_unified, etc.)
        project_id: Target project ID for cymonides-1-{projectId}
        root_entity: Optional root entity (the query subject)
        auto_create_types: List of node types to auto-create from records:
            - 'company': Create company nodes (default for companies_unified)
            - 'municipality': Create location nodes from city field
            - 'industry': Create industry nodes from industry field
            - 'country': Create country nodes from country field

    Returns:
        Summary of created nodes and edges
    """
    creator = ATLASNodeCreator(project_id=project_id)
    return creator.process_atlas_results(
        results, source_index, root_entity,
        auto_create_types=auto_create_types
    )


if __name__ == "__main__":
    # Test
    import asyncio

    async def test():
        # Simulate ATLAS company results
        test_results = [
            {
                'company_id': 'tax:12345',
                'name': 'Test Company Ltd',
                'domain': 'testcompany.com',
                'country': 'UK',
                'industry': 'Technology',
                'sources': ['wdc-organization']
            },
            {
                'company_id': 'domain:example.com',
                'name': 'Example Corp',
                'domain': 'example.com',
                'country': 'US',
                'sources': ['affiliate']
            }
        ]

        result = await create_nodes_from_atlas_results(
            results=test_results,
            source_index='companies_unified',
            project_id='test-project',
            root_entity={
                'type': 'query',
                'label': 'c: Test Company',
                'value': 'Test Company'
            }
        )

        print(f"Created {result['nodes_created']} nodes, {result['edges_created']} edges")
        print(f"Index: {result['index']}")
        print(f"Node IDs: {result['node_ids']}")

    asyncio.run(test())
