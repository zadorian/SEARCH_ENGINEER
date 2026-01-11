#!/usr/bin/env python3
"""
Entity Graph System for Corporella Claude
Creates nodes for all entities and bidirectional edges between them
"""

import sqlite3
import json
import hashlib
from typing import Dict, List, Tuple, Any, Optional
from datetime import datetime
from pathlib import Path


class EntityRelationshipMap:
    """
    Maps field contexts to relationship types and their inverses
    """

    # Bidirectional relationship mappings
    RELATIONSHIP_MAP = {
        # Corporate Relationships
        'subsidiary': {
            'forward': 'SUBSIDIARY_OF',
            'inverse': 'PARENT_OF',
            'forward_label': 'is subsidiary of',
            'inverse_label': 'owns/controls'
        },
        'parent_company': {
            'forward': 'PARENT_OF',
            'inverse': 'SUBSIDIARY_OF',
            'forward_label': 'owns/controls',
            'inverse_label': 'is subsidiary of'
        },
        'beneficial_owner': {
            'forward': 'OWNS',
            'inverse': 'OWNED_BY',
            'forward_label': 'beneficially owns',
            'inverse_label': 'is beneficially owned by'
        },

        # Officer Relationships
        'officer': {
            'forward': 'OFFICER_OF',
            'inverse': 'HAS_OFFICER',
            'forward_label': 'is officer of',
            'inverse_label': 'has officer'
        },
        'director': {
            'forward': 'DIRECTOR_OF',
            'inverse': 'HAS_DIRECTOR',
            'forward_label': 'is director of',
            'inverse_label': 'has director'
        },
        'secretary': {
            'forward': 'SECRETARY_OF',
            'inverse': 'HAS_SECRETARY',
            'forward_label': 'is secretary of',
            'inverse_label': 'has secretary'
        },
        'ceo': {
            'forward': 'CEO_OF',
            'inverse': 'HAS_CEO',
            'forward_label': 'is CEO of',
            'inverse_label': 'has CEO'
        },

        # Location Relationships
        'registered_address': {
            'forward': 'REGISTERED_AT',
            'inverse': 'REGISTRATION_ADDRESS_FOR',
            'forward_label': 'is registered at',
            'inverse_label': 'is registration address for'
        },
        'headquarters': {
            'forward': 'HEADQUARTERED_AT',
            'inverse': 'HEADQUARTERS_FOR',
            'forward_label': 'is headquartered at',
            'inverse_label': 'is headquarters for'
        },

        # Contact Relationships
        'email': {
            'forward': 'HAS_EMAIL',
            'inverse': 'EMAIL_FOR',
            'forward_label': 'has email',
            'inverse_label': 'is email for'
        },
        'phone': {
            'forward': 'HAS_PHONE',
            'inverse': 'PHONE_FOR',
            'forward_label': 'has phone',
            'inverse_label': 'is phone for'
        },

        # Legal Relationships
        'litigation': {
            'forward': 'INVOLVED_IN_LITIGATION',
            'inverse': 'LITIGATION_INVOLVES',
            'forward_label': 'is involved in litigation',
            'inverse_label': 'involves'
        },
        'regulator': {
            'forward': 'REGULATED_BY',
            'inverse': 'REGULATES',
            'forward_label': 'is regulated by',
            'inverse_label': 'regulates'
        }
    }

    @classmethod
    def get_relationship(cls, field_name: str, context: str = None) -> Dict:
        """Get relationship type based on field name and context"""

        # Normalize field name
        field_lower = field_name.lower()

        # Check for exact matches first
        for key in cls.RELATIONSHIP_MAP:
            if key in field_lower:
                return cls.RELATIONSHIP_MAP[key]

        # Context-based inference
        if context:
            context_lower = context.lower()
            if 'ownership' in context_lower:
                return cls.RELATIONSHIP_MAP['beneficial_owner']
            elif 'officer' in context_lower or 'director' in context_lower:
                return cls.RELATIONSHIP_MAP['officer']
            elif 'address' in context_lower:
                return cls.RELATIONSHIP_MAP['registered_address']

        # Default relationship for unknown fields
        return {
            'forward': 'RELATED_TO',
            'inverse': 'RELATED_TO',
            'forward_label': 'is related to',
            'inverse_label': 'is related to'
        }


class EntityGraph:
    """
    Manages the entity graph database with nodes and edges
    """

    def __init__(self, db_path: Optional[str] = None):
        """Initialize the entity graph system"""

        # Use existing database or create new
        if db_path:
            self.db_path = db_path
        else:
            # Try to use Corporella's existing database
            self.db_path = str(Path(__file__).parent.parent / "corporella_data.db")

        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row

        # Create/update schema
        self._init_schema()

        # Initialize relationship mapper
        self.relationship_map = EntityRelationshipMap()

    def _init_schema(self):
        """Initialize or update the graph schema"""

        cursor = self.conn.cursor()

        # Drop old nodes table if it has wrong schema
        cursor.execute("DROP TABLE IF EXISTS nodes")

        # Create new nodes table with expanded entity types
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS entity_nodes (
                id TEXT PRIMARY KEY,
                entity_type TEXT NOT NULL CHECK(entity_type IN (
                    'company', 'person', 'address', 'email', 'phone',
                    'url', 'litigation', 'regulator', 'document', 'other'
                )),
                name TEXT NOT NULL,
                normalized_name TEXT NOT NULL,
                properties TEXT,  -- JSON with all entity-specific properties
                sources TEXT,     -- JSON array of data sources
                first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(normalized_name, entity_type)
            )
        """)

        # Create edges table for relationships
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS entity_edges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                relationship_type TEXT NOT NULL,
                relationship_label TEXT,
                properties TEXT,  -- JSON with edge-specific properties
                field_context TEXT,  -- Which field this relationship came from
                confidence REAL DEFAULT 1.0,
                source TEXT,  -- Data source for this edge
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (source_id) REFERENCES entity_nodes(id),
                FOREIGN KEY (target_id) REFERENCES entity_nodes(id),
                UNIQUE(source_id, target_id, relationship_type)
            )
        """)

        # Create indexes for performance
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_nodes_type
            ON entity_nodes(entity_type)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_nodes_normalized
            ON entity_nodes(normalized_name)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_edges_source
            ON entity_edges(source_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_edges_target
            ON entity_edges(target_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_edges_relationship
            ON entity_edges(relationship_type)
        """)

        self.conn.commit()

    def _generate_node_id(self, entity_type: str, name: str) -> str:
        """Generate unique ID for a node"""
        normalized = self._normalize_name(name)
        content = f"{entity_type}:{normalized}"
        return hashlib.md5(content.encode()).hexdigest()

    def _normalize_name(self, name: str) -> str:
        """Normalize entity name for comparison"""
        if not name:
            return ""
        # Remove extra spaces, convert to lowercase, strip
        return " ".join(name.lower().strip().split())

    def create_node(self, entity_type: str, name: str,
                   properties: Dict = None, sources: List[str] = None) -> str:
        """
        Create or update an entity node
        Returns the node ID
        """

        node_id = self._generate_node_id(entity_type, name)
        normalized_name = self._normalize_name(name)

        cursor = self.conn.cursor()

        # Check if node exists
        cursor.execute("""
            SELECT id, properties, sources
            FROM entity_nodes
            WHERE id = ?
        """, (node_id,))

        existing = cursor.fetchone()

        if existing:
            # Merge properties and sources
            existing_props = json.loads(existing['properties'] or '{}')
            existing_sources = json.loads(existing['sources'] or '[]')

            if properties:
                existing_props.update(properties)
            if sources:
                existing_sources.extend([s for s in sources if s not in existing_sources])

            # Update existing node
            cursor.execute("""
                UPDATE entity_nodes
                SET properties = ?, sources = ?, last_updated = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (json.dumps(existing_props), json.dumps(existing_sources), node_id))

        else:
            # Create new node
            cursor.execute("""
                INSERT INTO entity_nodes
                (id, entity_type, name, normalized_name, properties, sources)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                node_id,
                entity_type,
                name,
                normalized_name,
                json.dumps(properties or {}),
                json.dumps(sources or [])
            ))

        self.conn.commit()
        return node_id

    def create_edge(self, source_id: str, target_id: str,
                   relationship_type: str, relationship_label: str = None,
                   field_context: str = None, properties: Dict = None,
                   source: str = None, confidence: float = 1.0) -> bool:
        """Create an edge between two nodes"""

        cursor = self.conn.cursor()

        try:
            cursor.execute("""
                INSERT OR REPLACE INTO entity_edges
                (source_id, target_id, relationship_type, relationship_label,
                 properties, field_context, confidence, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                source_id, target_id, relationship_type, relationship_label,
                json.dumps(properties or {}), field_context, confidence, source
            ))
            self.conn.commit()
            return True

        except sqlite3.IntegrityError:
            # Edge already exists or nodes don't exist
            return False

    def create_bidirectional_edge(self, entity1_id: str, entity2_id: str,
                                 field_context: str, is_forward: bool = True,
                                 properties: Dict = None, source: str = None) -> Tuple[bool, bool]:
        """
        Create bidirectional edges based on field context
        Returns tuple of (forward_success, inverse_success)
        """

        relationship = self.relationship_map.get_relationship(field_context)

        if is_forward:
            # Create forward edge
            forward_success = self.create_edge(
                entity1_id, entity2_id,
                relationship['forward'],
                relationship['forward_label'],
                field_context, properties, source
            )

            # Create inverse edge
            inverse_success = self.create_edge(
                entity2_id, entity1_id,
                relationship['inverse'],
                relationship['inverse_label'],
                field_context, properties, source
            )
        else:
            # Reverse the direction
            forward_success = self.create_edge(
                entity1_id, entity2_id,
                relationship['inverse'],
                relationship['inverse_label'],
                field_context, properties, source
            )

            inverse_success = self.create_edge(
                entity2_id, entity1_id,
                relationship['forward'],
                relationship['forward_label'],
                field_context, properties, source
            )

        return (forward_success, inverse_success)

    def get_node_relationships(self, node_id: str,
                              relationship_type: str = None) -> List[Dict]:
        """Get all relationships for a node"""

        cursor = self.conn.cursor()

        if relationship_type:
            # Get specific relationship type
            query = """
                SELECT e.*, n.name as target_name, n.entity_type as target_type
                FROM entity_edges e
                JOIN entity_nodes n ON e.target_id = n.id
                WHERE e.source_id = ? AND e.relationship_type = ?

                UNION

                SELECT e.*, n.name as target_name, n.entity_type as target_type
                FROM entity_edges e
                JOIN entity_nodes n ON e.source_id = n.id
                WHERE e.target_id = ? AND e.relationship_type = ?
            """
            cursor.execute(query, (node_id, relationship_type, node_id, relationship_type))
        else:
            # Get all relationships
            query = """
                SELECT e.*, n.name as target_name, n.entity_type as target_type,
                       'outgoing' as direction
                FROM entity_edges e
                JOIN entity_nodes n ON e.target_id = n.id
                WHERE e.source_id = ?

                UNION

                SELECT e.*, n.name as target_name, n.entity_type as target_type,
                       'incoming' as direction
                FROM entity_edges e
                JOIN entity_nodes n ON e.source_id = n.id
                WHERE e.target_id = ?
            """
            cursor.execute(query, (node_id, node_id))

        relationships = []
        for row in cursor.fetchall():
            rel = dict(row)
            if rel.get('properties'):
                rel['properties'] = json.loads(rel['properties'])
            relationships.append(rel)

        return relationships

    def get_node(self, node_id: str) -> Optional[Dict]:
        """Get a node by ID"""

        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM entity_nodes WHERE id = ?
        """, (node_id,))

        row = cursor.fetchone()
        if row:
            node = dict(row)
            if node.get('properties'):
                node['properties'] = json.loads(node['properties'])
            if node.get('sources'):
                node['sources'] = json.loads(node['sources'])
            return node
        return None

    def find_nodes_by_name(self, name: str, entity_type: str = None) -> List[Dict]:
        """Find nodes by name (partial match)"""

        cursor = self.conn.cursor()
        normalized = self._normalize_name(name)

        if entity_type:
            cursor.execute("""
                SELECT * FROM entity_nodes
                WHERE normalized_name LIKE ? AND entity_type = ?
            """, (f"%{normalized}%", entity_type))
        else:
            cursor.execute("""
                SELECT * FROM entity_nodes
                WHERE normalized_name LIKE ?
            """, (f"%{normalized}%",))

        nodes = []
        for row in cursor.fetchall():
            node = dict(row)
            if node.get('properties'):
                node['properties'] = json.loads(node['properties'])
            if node.get('sources'):
                node['sources'] = json.loads(node['sources'])
            nodes.append(node)

        return nodes

    def extract_and_create_entities(self, company_data: Dict,
                                   company_id: str, source: str = None) -> Dict[str, List[str]]:
        """
        Extract all entities from company data and create nodes/edges
        Returns dict of entity_type -> list of node_ids
        """

        created_entities = {
            'companies': [],
            'people': [],
            'addresses': [],
            'emails': [],
            'phones': []
        }

        # Extract officers/people
        officers = company_data.get('officers', [])
        if isinstance(officers, str):
            officers = json.loads(officers)

        for officer in officers:
            if isinstance(officer, dict) and officer.get('name'):
                person_id = self.create_node(
                    'person',
                    officer['name'],
                    properties={
                        'position': officer.get('position'),
                        'appointed_on': officer.get('appointed_on'),
                        'nationality': officer.get('nationality'),
                        'occupation': officer.get('occupation')
                    },
                    sources=[source] if source else []
                )
                created_entities['people'].append(person_id)

                # Create relationship to company
                self.create_bidirectional_edge(
                    person_id, company_id,
                    field_context=officer.get('position', 'officer'),
                    source=source
                )

        # Extract ownership/subsidiary companies
        ownership = company_data.get('ownership', {})
        if isinstance(ownership, str):
            ownership = json.loads(ownership)

        # Process beneficial owners
        beneficial_owners = ownership.get('beneficial_owners', [])
        for owner in beneficial_owners:
            if isinstance(owner, dict) and owner.get('name'):
                # Determine if owner is company or person
                entity_type = 'company' if any(suffix in owner['name'].lower()
                                              for suffix in ['ltd', 'inc', 'corp', 'llc']) else 'person'

                owner_id = self.create_node(
                    entity_type,
                    owner['name'],
                    properties={
                        'ownership_percentage': owner.get('percentage'),
                        'ownership_type': owner.get('type')
                    },
                    sources=[source] if source else []
                )

                if entity_type == 'company':
                    created_entities['companies'].append(owner_id)
                else:
                    created_entities['people'].append(owner_id)

                # Create ownership relationship
                self.create_bidirectional_edge(
                    owner_id, company_id,
                    field_context='beneficial_owner',
                    properties={'percentage': owner.get('percentage')},
                    source=source
                )

        # Process subsidiaries
        subsidiaries = ownership.get('subsidiaries', [])
        for subsidiary in subsidiaries:
            if isinstance(subsidiary, dict) and subsidiary.get('name'):
                sub_id = self.create_node(
                    'company',
                    subsidiary['name'],
                    properties={
                        'ownership_percentage': subsidiary.get('percentage'),
                        'jurisdiction': subsidiary.get('jurisdiction')
                    },
                    sources=[source] if source else []
                )
                created_entities['companies'].append(sub_id)

                # Create subsidiary relationship
                self.create_bidirectional_edge(
                    sub_id, company_id,
                    field_context='subsidiary',
                    properties={'percentage': subsidiary.get('percentage')},
                    source=source
                )

        # Extract addresses
        locations = company_data.get('locations', {})
        if isinstance(locations, str):
            locations = json.loads(locations)

        for location_type, address_data in locations.items():
            if isinstance(address_data, dict) and address_data.get('value'):
                address_id = self.create_node(
                    'address',
                    address_data['value'],
                    properties={'type': location_type},
                    sources=address_data.get('source', [])
                )
                created_entities['addresses'].append(address_id)

                # Create location relationship
                self.create_bidirectional_edge(
                    company_id, address_id,
                    field_context=location_type,
                    source=source
                )

        return created_entities

    def close(self):
        """Close database connection"""
        self.conn.close()


if __name__ == "__main__":
    # Test the entity graph system
    graph = EntityGraph()

    # Create some test entities
    company_id = graph.create_node(
        'company',
        'Apple Inc',
        properties={'jurisdiction': 'us_ca', 'company_number': 'C0806592'},
        sources=['opencorporates']
    )

    person_id = graph.create_node(
        'person',
        'Tim Cook',
        properties={'position': 'CEO'},
        sources=['opencorporates']
    )

    # Create bidirectional relationship
    graph.create_bidirectional_edge(
        person_id, company_id,
        field_context='ceo',
        source='opencorporates'
    )

    # Get relationships
    relationships = graph.get_node_relationships(company_id)
    print(f"Company relationships: {json.dumps(relationships, indent=2)}")

    person_relationships = graph.get_node_relationships(person_id)
    print(f"Person relationships: {json.dumps(person_relationships, indent=2)}")

    graph.close()