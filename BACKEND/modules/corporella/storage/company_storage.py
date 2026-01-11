"""
Corporella Company Storage Module
Integrates with Search Engineer's SQL database for persistent company data storage
"""

import sqlite3
import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List, Union
import logging
from .entity_graph import EntityGraph

logger = logging.getLogger(__name__)

class CorporellaStorage:
    """Manages company data persistence in Search Engineer's SQL database"""

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize storage with database path

        Args:
            db_path: Path to SQLite database. If None, tries Search Engineer DB first,
                    then falls back to local database
        """
        if db_path:
            self.db_path = db_path
        else:
            # Try to use Search Engineer's database first
            search_engine_db = Path(__file__).parent.parent.parent / "search_graph.db"
            if search_engine_db.exists():
                self.db_path = str(search_engine_db)
                logger.info(f"Using Search Engineer database: {self.db_path}")
            else:
                # Fallback to local database
                self.db_path = str(Path(__file__).parent.parent / "corporella_data.db")
                logger.info(f"Using local database: {self.db_path}")

        self._init_database()

        # Initialize entity graph using the same database
        self.entity_graph = EntityGraph(self.db_path)

    def _init_database(self):
        """Initialize database tables if they don't exist"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Create company_entities table (compatible with Search Engineer schema)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS company_entities (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    normalized_name TEXT NOT NULL,
                    company_number TEXT,
                    jurisdiction TEXT,
                    founded_year INTEGER,
                    revenue TEXT,
                    employee_count INTEGER,
                    registered_address TEXT,
                    website TEXT,
                    sources TEXT,  -- JSON array of source badges
                    officers TEXT,  -- JSON array of officers
                    ownership_structure TEXT,  -- JSON for ownership
                    compliance TEXT,  -- JSON for compliance sections
                    wiki_sources TEXT,  -- JSON for wiki sources
                    raw_data TEXT,  -- Complete raw data from APIs
                    metadata TEXT,  -- Additional metadata
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create company_officers table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS company_officers (
                    id TEXT PRIMARY KEY,
                    company_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    position TEXT,
                    details TEXT,
                    start_date TEXT,
                    end_date TEXT,
                    source TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (company_id) REFERENCES company_entities(id)
                )
            """)

            # Create nodes table for graph integration
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS nodes (
                    id TEXT PRIMARY KEY,
                    node_type TEXT NOT NULL,
                    value TEXT NOT NULL,
                    value_hash TEXT,
                    project_id TEXT DEFAULT 'corporella',
                    meta TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create entity_metadata table if not exists (for Search Engineer compatibility)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS entity_metadata (
                    id TEXT PRIMARY KEY,
                    entity_type TEXT CHECK(entity_type IN ('email', 'phone', 'person', 'company',
                                                           'organization', 'address', 'url',
                                                           'username', 'city', 'region',
                                                           'country', 'red_flag', 'vehicle',
                                                           'password')),
                    normalized_value TEXT NOT NULL,
                    display_value TEXT NOT NULL,
                    variations TEXT,
                    alias TEXT,
                    confidence REAL DEFAULT 1.0,
                    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    occurrence_count INTEGER DEFAULT 1,
                    extraction_method TEXT
                )
            """)

            # Create nodes table if not exists (for Search Engineer graph integration)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS nodes (
                    id TEXT PRIMARY KEY,
                    node_type TEXT CHECK(node_type IN ('query', 'url', 'entity',
                                                       'narrative', 'profile', 'book')),
                    value TEXT NOT NULL,
                    value_hash TEXT NOT NULL,
                    project_id TEXT DEFAULT 'corporella',
                    meta TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            conn.commit()

    def _generate_id(self, name: str, jurisdiction: Optional[str] = None) -> str:
        """Generate unique ID for company"""
        id_string = f"{name.lower()}_{jurisdiction or 'unknown'}"
        return hashlib.md5(id_string.encode()).hexdigest()

    def _normalize_name(self, name: str) -> str:
        """Normalize company name for searching"""
        # Remove common suffixes and normalize
        normalized = name.upper()
        for suffix in [' LTD', ' LIMITED', ' INC', ' CORP', ' CORPORATION', ' LLC', ' PLC', ' LP']:
            normalized = normalized.replace(suffix, '')
        return normalized.strip()

    def save_company(self, entity_dict: Dict[str, Any]) -> str:
        """
        Save company entity to database

        Args:
            entity_dict: Corporella entity dictionary

        Returns:
            Company ID
        """
        # Extract basic fields
        name = entity_dict.get('name', {}).get('value', '')
        if not name:
            raise ValueError("Company name is required")

        about = entity_dict.get('about', {})
        company_number = about.get('company_number', '')
        jurisdiction = about.get('jurisdiction', '')

        # Generate IDs
        company_id = self._generate_id(name, jurisdiction)
        normalized_name = self._normalize_name(name)

        # Extract complex fields as JSON
        sources = []
        if entity_dict.get('_raw_results'):
            for result in entity_dict['_raw_results']:
                if result.get('ok') and result.get('source'):
                    sources.append(result['source'])

        officers_json = json.dumps(entity_dict.get('officers', []))
        ownership_json = json.dumps(entity_dict.get('ownership_structure', {}))
        compliance_json = json.dumps(entity_dict.get('compliance', {}))

        # Extract wiki sources
        wiki_sources = {}
        for section in ['litigation', 'regulatory', 'assets', 'licensing', 'political', 'reputation', 'other']:
            wiki_key = f"compliance_{section}_wiki_sources"
            if wiki_key in entity_dict:
                wiki_sources[section] = entity_dict[wiki_key]
        wiki_sources_json = json.dumps(wiki_sources)

        # Store raw data
        raw_data = json.dumps(entity_dict.get('_raw_results', []))

        # Additional metadata
        metadata = {
            'variations': entity_dict.get('name', {}).get('variations', ''),
            'alias': entity_dict.get('name', {}).get('alias', ''),
            'incorporation_date': about.get('incorporation_date', ''),
            'status': about.get('status', ''),
            'activity': entity_dict.get('activity', ''),
            'filings': entity_dict.get('filings', []),
            'notes': entity_dict.get('notes', '')
        }
        metadata_json = json.dumps(metadata)

        # Save to database
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Check if company exists
            cursor.execute("SELECT id FROM company_entities WHERE id = ?", (company_id,))
            exists = cursor.fetchone() is not None

            if exists:
                # Update existing record
                cursor.execute("""
                    UPDATE company_entities SET
                        name = ?,
                        normalized_name = ?,
                        company_number = ?,
                        jurisdiction = ?,
                        founded_year = ?,
                        revenue = ?,
                        employee_count = ?,
                        registered_address = ?,
                        website = ?,
                        sources = ?,
                        officers = ?,
                        ownership_structure = ?,
                        compliance = ?,
                        wiki_sources = ?,
                        raw_data = ?,
                        metadata = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (
                    name,
                    normalized_name,
                    company_number,
                    jurisdiction,
                    about.get('founded_year'),
                    entity_dict.get('financial_results', ''),
                    None,  # employee_count - not in current schema
                    about.get('registered_address', {}).get('value', ''),
                    about.get('website', {}).get('value', ''),
                    json.dumps(sources),
                    officers_json,
                    ownership_json,
                    compliance_json,
                    wiki_sources_json,
                    raw_data,
                    metadata_json,
                    company_id
                ))
            else:
                # Insert new record
                cursor.execute("""
                    INSERT INTO company_entities (
                        id, name, normalized_name, company_number, jurisdiction,
                        founded_year, revenue, employee_count, registered_address, website,
                        sources, officers, ownership_structure, compliance, wiki_sources,
                        raw_data, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    company_id,
                    name,
                    normalized_name,
                    company_number,
                    jurisdiction,
                    about.get('founded_year'),
                    entity_dict.get('financial_results', ''),
                    None,  # employee_count
                    about.get('registered_address', {}).get('value', ''),
                    about.get('website', {}).get('value', ''),
                    json.dumps(sources),
                    officers_json,
                    ownership_json,
                    compliance_json,
                    wiki_sources_json,
                    raw_data,
                    metadata_json
                ))

            # Save officers to separate table
            self._save_officers(cursor, company_id, entity_dict.get('officers', []))

            # Add to entity_metadata for Search Engineer compatibility
            self._save_entity_metadata(cursor, company_id, name, normalized_name, metadata)

            conn.commit()

        # Extract and create all entities in the graph
        try:
            extracted_entities = self.entity_graph.extract_and_create_entities(
                entity_dict,
                company_id,
                'corporella'
            )
            logger.info(f"Extracted entities for {name}: {extracted_entities}")
        except Exception as e:
            logger.warning(f"Failed to extract entities to graph: {e}")
            # Don't fail the save if graph extraction fails

        logger.info(f"Saved company {name} (ID: {company_id})")
        return company_id

    def _save_officers(self, cursor, company_id: str, officers: List[Dict]):
        """Save officers to company_officers table"""
        # Delete existing officers
        cursor.execute("DELETE FROM company_officers WHERE company_id = ?", (company_id,))

        # Insert new officers
        for officer in officers:
            if officer.get('name'):
                officer_id = hashlib.md5(f"{company_id}_{officer['name']}_{officer.get('type', officer.get('position', ''))}".encode()).hexdigest()

                # Handle source as either string or list
                source = officer.get('source', '')
                if isinstance(source, list):
                    source = ', '.join(source)  # Convert list to comma-separated string

                cursor.execute("""
                    INSERT INTO company_officers (
                        id, company_id, name, position, details, source
                    ) VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    officer_id,
                    company_id,
                    officer['name'],
                    officer.get('type', officer.get('position', '')),  # Support both type and position
                    officer.get('details', officer.get('appointed_on', '')),  # Support both details and appointed_on
                    source
                ))

    def _save_entity_metadata(self, cursor, company_id: str, name: str,
                             normalized_name: str, metadata: Dict):
        """Save to entity_metadata for Search Engineer compatibility"""
        cursor.execute("""
            INSERT OR REPLACE INTO entity_metadata (
                id, entity_type, normalized_value, display_value,
                variations, alias, extraction_method
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            company_id,
            'company',
            normalized_name,
            name,
            metadata.get('variations', ''),
            metadata.get('alias', ''),
            'corporella'
        ))

    def _save_node(self, cursor, company_id: str, name: str, entity_dict: Dict):
        """Save to nodes table for graph integration"""
        value_hash = hashlib.md5(name.encode()).hexdigest()
        meta = {
            'entity_type': 'company',
            'source': 'corporella',
            'jurisdiction': entity_dict.get('about', {}).get('jurisdiction', ''),
            'company_number': entity_dict.get('about', {}).get('company_number', '')
        }

        cursor.execute("""
            INSERT OR REPLACE INTO nodes (
                id, node_type, value, value_hash, project_id, meta
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            company_id,
            'entity',
            name,
            value_hash,
            'corporella',
            json.dumps(meta)
        ))

    def load_company(self, company_name: str, jurisdiction: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Load company entity from database

        Args:
            company_name: Company name to search for
            jurisdiction: Optional jurisdiction to narrow search

        Returns:
            Corporella entity dictionary or None if not found
        """
        normalized_name = self._normalize_name(company_name)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Search by normalized name and optionally jurisdiction
            if jurisdiction:
                cursor.execute("""
                    SELECT * FROM company_entities
                    WHERE normalized_name = ? AND jurisdiction = ?
                    ORDER BY updated_at DESC LIMIT 1
                """, (normalized_name, jurisdiction))
            else:
                cursor.execute("""
                    SELECT * FROM company_entities
                    WHERE normalized_name = ?
                    ORDER BY updated_at DESC LIMIT 1
                """, (normalized_name,))

            row = cursor.fetchone()

            if not row:
                return None

            # Convert row to dictionary
            columns = [col[0] for col in cursor.description]
            company_data = dict(zip(columns, row))

            # Reconstruct Corporella entity format
            entity = {
                'id': company_data['id'],
                'name': {
                    'value': company_data['name']
                },
                'node_class': 'entity',
                'type': 'company',
                'about': {
                    'company_number': company_data['company_number'] or '',
                    'jurisdiction': company_data['jurisdiction'] or '',
                    'founded_year': company_data['founded_year'],
                    'registered_address': {
                        'value': company_data['registered_address'] or '',
                        'source': ''
                    },
                    'website': {
                        'value': company_data['website'] or '',
                        'source': ''
                    }
                },
                'financial_results': company_data['revenue'] or '',
                'officers': json.loads(company_data['officers'] or '[]'),
                'ownership_structure': json.loads(company_data['ownership_structure'] or '{}'),
                'compliance': json.loads(company_data['compliance'] or '{}')
            }

            # Add metadata
            metadata = json.loads(company_data['metadata'] or '{}')
            entity['name']['variations'] = metadata.get('variations', '')
            entity['name']['alias'] = metadata.get('alias', '')
            entity['about']['incorporation_date'] = metadata.get('incorporation_date', '')
            entity['about']['status'] = metadata.get('status', '')
            entity['activity'] = metadata.get('activity', '')
            entity['filings'] = metadata.get('filings', [])
            entity['notes'] = metadata.get('notes', '')

            # Add wiki sources
            wiki_sources = json.loads(company_data['wiki_sources'] or '{}')
            for section, sources in wiki_sources.items():
                entity[f'compliance_{section}_wiki_sources'] = sources

            # Add raw results
            entity['_raw_results'] = json.loads(company_data['raw_data'] or '[]')

            # Load officers from separate table
            cursor.execute("""
                SELECT * FROM company_officers
                WHERE company_id = ?
                ORDER BY created_at
            """, (company_data['id'],))

            officers = []
            for officer_row in cursor.fetchall():
                officer_cols = [col[0] for col in cursor.description]
                officer_data = dict(zip(officer_cols, officer_row))
                officers.append({
                    'type': officer_data['position'] or '',
                    'name': officer_data['name'],
                    'details': officer_data['details'] or '',
                    'source': officer_data['source'] or ''
                })

            if officers:
                entity['officers'] = officers

            logger.info(f"Loaded company {company_name} from database")
            return entity

    def get_entity_relationships(self, company_id: str) -> Dict[str, Any]:
        """
        Get all entity relationships for a company from the graph

        Args:
            company_id: The company's unique ID

        Returns:
            Dictionary containing all relationships and connected entities
        """
        try:
            relationships = self.entity_graph.get_node_relationships(company_id)

            # Organize relationships into outgoing and incoming
            outgoing = []
            incoming = []

            for rel in relationships:
                # Determine if this is outgoing or incoming based on source_id
                if rel.get('source_id') == company_id:
                    outgoing.append(rel)
                elif rel.get('target_id') == company_id:
                    incoming.append(rel)

            return {
                "outgoing": outgoing,
                "incoming": incoming,
                "total": len(relationships)
            }
        except Exception as e:
            logger.warning(f"Failed to get entity relationships: {e}")
            return {
                "outgoing": [],
                "incoming": [],
                "error": str(e)
            }

    def update_company(self, company_name_or_id: str,
                      jurisdiction_or_updates: Optional[Union[str, Dict[str, Any]]] = None,
                      entity_dict: Optional[Dict[str, Any]] = None) -> bool:
        """
        Update specific fields of a company entity
        Supports two signatures:
        1. update_company(company_id, updates_dict)
        2. update_company(company_name, jurisdiction, entity_dict)

        Args:
            company_name_or_id: Company ID or company name
            jurisdiction_or_updates: Jurisdiction code or updates dict
            entity_dict: Full entity dict (when using signature 2)
            updates: Dictionary of fields to update

        Returns:
            True if successful
        """
        # Handle both signatures
        if entity_dict is not None:
            # Signature 2: company_name, jurisdiction, entity_dict
            # Just save the entire entity (it will replace existing one)
            return self.save_company(entity_dict) is not None
        else:
            # Signature 1: company_id, updates_dict
            company_id = company_name_or_id
            updates = jurisdiction_or_updates if isinstance(jurisdiction_or_updates, dict) else {}

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Build update query dynamically
            update_fields = []
            values = []

            # Map Corporella fields to database columns
            field_mapping = {
                'name.value': 'name',
                'about.company_number': 'company_number',
                'about.jurisdiction': 'jurisdiction',
                'about.founded_year': 'founded_year',
                'about.registered_address.value': 'registered_address',
                'about.website.value': 'website',
                'financial_results': 'revenue'
            }

            for corporella_field, db_field in field_mapping.items():
                if corporella_field in updates:
                    update_fields.append(f"{db_field} = ?")
                    values.append(updates[corporella_field])

            # Handle complex fields
            if 'officers' in updates:
                update_fields.append("officers = ?")
                values.append(json.dumps(updates['officers']))
                self._save_officers(cursor, company_id, updates['officers'])

            if 'ownership_structure' in updates:
                update_fields.append("ownership_structure = ?")
                values.append(json.dumps(updates['ownership_structure']))

            if 'compliance' in updates:
                update_fields.append("compliance = ?")
                values.append(json.dumps(updates['compliance']))

            if update_fields:
                update_fields.append("updated_at = CURRENT_TIMESTAMP")
                values.append(company_id)

                query = f"UPDATE company_entities SET {', '.join(update_fields)} WHERE id = ?"
                cursor.execute(query, values)
                conn.commit()

                logger.info(f"Updated company {company_id}")
                return True

        return False

    def search_companies(self, search_term: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Search for companies by name

        Args:
            search_term: Search term
            limit: Maximum number of results

        Returns:
            List of company summaries
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Search in both name and normalized_name
            cursor.execute("""
                SELECT id, name, company_number, jurisdiction,
                       founded_year, updated_at
                FROM company_entities
                WHERE name LIKE ? OR normalized_name LIKE ?
                ORDER BY updated_at DESC
                LIMIT ?
            """, (f'%{search_term}%', f'%{search_term.upper()}%', limit))

            results = []
            for row in cursor.fetchall():
                results.append({
                    'id': row[0],
                    'name': row[1],
                    'company_number': row[2],
                    'jurisdiction': row[3],
                    'founded_year': row[4],
                    'last_updated': row[5]
                })

            return results

    def get_stats(self) -> Dict[str, int]:
        """Get database statistics"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            stats = {}

            # Count companies
            cursor.execute("SELECT COUNT(*) FROM company_entities")
            stats['companies'] = cursor.fetchone()[0]

            # Count officers
            cursor.execute("SELECT COUNT(*) FROM company_officers")
            stats['officers'] = cursor.fetchone()[0]

            # Count entities
            cursor.execute("SELECT COUNT(*) FROM entity_metadata WHERE entity_type = 'company'")
            stats['entity_metadata'] = cursor.fetchone()[0]

            # Count nodes
            cursor.execute("SELECT COUNT(*) FROM nodes WHERE node_type = 'entity'")
            stats['nodes'] = cursor.fetchone()[0]

            return stats