#!/usr/bin/env python3
"""
WikiMan Template-Based Output Formatter
Ensures all entity searches are saved using the proper JSON templates
NOW WITH SQL DATABASE INTEGRATION FOR PERSISTENT GRAPH STORAGE
"""

import json
import os
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
import sys

# Add paths for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / 'TOOLS' / 'Ingestion'))

# Import graph database
from wikiman_graph_db import WikiManGraphDB

class WikiManTemplateFormatter:
    """Format and save WikiMan outputs using entity templates"""
    
    def __init__(self, save_to_db: bool = True):
        self.templates_dir = Path("/Users/attic/Library/Mobile Documents/com~apple~CloudDocs/01_ACTIVE_PROJECTS/Development/Search-Engineer.02/ii. SUBJECT/ENTITY")
        self.output_dir = Path.cwd() / 'wikiman_entity_outputs'
        self.output_dir.mkdir(exist_ok=True)
        
        # Load all entity templates
        self.templates = self._load_all_templates()
        
        # Track session entities for graph building
        self.session_entities = []
        self.session_edges = []
        
        # Initialize graph database
        self.save_to_db = save_to_db
        if self.save_to_db:
            self.graph_db = WikiManGraphDB()
            print(f"💾 Connected to WikiMan Graph DB: {self.graph_db.db_path}")
        
    def _load_all_templates(self) -> Dict[str, Dict]:
        """Load all entity templates from Ingestion folder"""
        templates = {}
        
        template_files = [
            'email_entity_template.json',
            'person_entity_template.json', 
            'company_entity_template.json',
            'organization_entity_template.json',
            'phone_entity_template.json',
            'username_entity_template.json',
            'password_entity_template.json',
            'url_entity_template.json',
            'address_entity_template.json',
            'vehicle_entity_template.json',
            'intellectual_property_entity_template.json',
            'art_entity_template.json',
            'ip_address_entity_template.json',
            'country_entity_template.json',
            'region_entity_template.json',
            'municipality_entity_template.json'
        ]
        
        for template_file in template_files:
            template_path = self.templates_dir / template_file
            if template_path.exists():
                with open(template_path, 'r') as f:
                    entity_type = template_file.replace('_entity_template.json', '')
                    templates[entity_type] = json.load(f)
                    print(f"✅ Loaded template: {entity_type}")
        
        return templates
    
    def format_entity_result(self, entity_type: str, raw_data: Dict, search_context: Dict = None) -> Dict:
        """
        Format raw search results into proper template structure
        
        Args:
            entity_type: Type of entity (email, person, company, etc.)
            raw_data: Raw search results from OSINT tools
            search_context: Additional context (query, source, etc.)
        """
        
        # Get the appropriate template
        template = self.templates.get(entity_type)
        if not template:
            print(f"⚠️ No template found for {entity_type}, using generic format")
            return self._generic_format(entity_type, raw_data)
        
        # Create formatted entity based on template
        formatted = self._populate_template(template, raw_data, entity_type)
        
        # Add metadata
        formatted['_metadata'] = {
            'entity_type': entity_type,
            'search_date': datetime.utcnow().isoformat() + 'Z',
            'search_context': search_context or {},
            'sources': self._extract_sources(raw_data),
            'template_version': template.get('metadata', {}).get('version', '1.0')
        }
        
        # Generate node ID for graph
        formatted['node_id'] = self._generate_node_id(entity_type, formatted.get('value', ''))
        
        return formatted
    
    def _populate_template(self, template: Dict, raw_data: Dict, entity_type: str) -> Dict:
        """Populate template fields with data from raw results"""
        
        formatted = {}
        
        # Handle different entity types
        if entity_type == 'email':
            formatted = self._format_email(template, raw_data)
        elif entity_type == 'person':
            formatted = self._format_person(template, raw_data)
        elif entity_type == 'company':
            formatted = self._format_company(template, raw_data)
        elif entity_type == 'organization':
            formatted = self._format_organization(template, raw_data)
        elif entity_type == 'phone':
            formatted = self._format_phone(template, raw_data)
        elif entity_type == 'username':
            formatted = self._format_username(template, raw_data)
        elif entity_type == 'url' or entity_type == 'domain':
            formatted = self._format_url(template, raw_data)
        elif entity_type == 'ip_address':
            formatted = self._format_ip(template, raw_data)
        else:
            # Generic population
            formatted = self._generic_populate(template, raw_data)
        
        return formatted
    
    def _format_email(self, template: Dict, raw_data: Dict) -> Dict:
        """Format email entity with template"""
        formatted = template.copy()
        
        # Extract email value
        email = raw_data.get('email') or raw_data.get('value', '')
        formatted['value'] = email
        formatted['name'] = email
        
        # Parse domain and username
        if '@' in email:
            username, domain = email.split('@', 1)
            formatted['domain'] = domain
            formatted['username'] = username
        
        # Breach information
        if 'breaches' in raw_data or 'breach_count' in raw_data:
            formatted['breach_status'] = 'compromised'
            formatted['breach_count'] = raw_data.get('breach_count', 0)
            
            # Extract breach sources
            breaches = raw_data.get('breaches', [])
            breach_sources = []
            for breach in breaches[:10]:  # First 10
                if isinstance(breach, dict):
                    breach_name = breach.get('database_name') or breach.get('name', 'Unknown')
                    breach_sources.append(breach_name)
            formatted['breach_sources'] = breach_sources
        
        # Associated data
        formatted['associated_usernames'] = raw_data.get('usernames', [])
        formatted['associated_phones'] = raw_data.get('phones', [])
        
        # Professional info if from RocketReach
        if 'professional_data' in raw_data:
            prof = raw_data['professional_data']
            formatted['owner_name'] = prof.get('name')
            formatted['owner_company'] = prof.get('current_employer')
            formatted['professional_status'] = 'verified'
        
        return formatted
    
    def _format_person(self, template: Dict, raw_data: Dict) -> Dict:
        """Format person entity with template"""
        formatted = template.copy()
        
        # Basic info
        formatted['value'] = raw_data.get('name') or raw_data.get('value', '')
        formatted['name'] = formatted['value']
        
        # Name variations
        variations = raw_data.get('variations', [])
        if variations:
            formatted['name_variations'] = variations
        
        # Professional info
        if 'professional_data' in raw_data:
            prof = raw_data['professional_data']
            formatted['occupation'] = prof.get('current_title')
            formatted['employer'] = prof.get('current_employer')
            formatted['location'] = prof.get('location')
            formatted['linkedin_url'] = prof.get('linkedin_url')
            formatted['emails'] = prof.get('emails', [])
            formatted['phones'] = prof.get('phones', [])
        
        # Breach exposure
        if 'breach_data' in raw_data:
            formatted['breach_exposure'] = True
            formatted['compromised_accounts'] = raw_data.get('breach_count', 0)
        
        return formatted
    
    def _format_company(self, template: Dict, raw_data: Dict) -> Dict:
        """Format company entity with template"""
        formatted = template.copy()
        
        formatted['value'] = raw_data.get('name') or raw_data.get('value', '')
        formatted['name'] = formatted['value']
        
        # Company details
        if 'unified' in raw_data:
            unified = raw_data['unified']
            formatted['industry'] = unified.get('industry')
            formatted['headquarters'] = unified.get('headquarters')
            formatted['revenue'] = unified.get('revenue')
            formatted['employees'] = unified.get('employees')
            formatted['website'] = unified.get('website')
            formatted['registration_number'] = unified.get('company_number')
        
        # OpenCorporates data
        if 'oc' in raw_data and raw_data['oc'].get('ok'):
            oc_data = raw_data['oc'].get('companies', [])
            if oc_data:
                company = oc_data[0] if isinstance(oc_data, list) else oc_data
                formatted['jurisdiction'] = company.get('jurisdiction')
                formatted['incorporation_date'] = company.get('incorporation_date')
                formatted['status'] = company.get('current_status')
                formatted['registry_url'] = company.get('registry_url')
        
        # Officers
        officers = []
        if 'officers' in raw_data:
            for officer in raw_data['officers'][:10]:  # First 10
                officers.append({
                    'name': officer.get('name'),
                    'position': officer.get('position'),
                    'start_date': officer.get('start_date')
                })
        formatted['officers'] = officers
        
        return formatted
    
    def _format_organization(self, template: Dict, raw_data: Dict) -> Dict:
        """Format organization (non-commercial) entity with template"""
        formatted = template.copy()
        
        formatted['value'] = raw_data.get('name') or raw_data.get('value', '')
        formatted['name'] = formatted['value']
        formatted['type'] = raw_data.get('org_type', 'government')
        
        # Distinguish from company
        formatted['entity_class'] = 'organization'  # Not company
        formatted['purpose'] = raw_data.get('purpose', 'public service')
        
        return formatted
    
    def _format_phone(self, template: Dict, raw_data: Dict) -> Dict:
        """Format phone entity with template"""
        formatted = template.copy()
        
        phone = raw_data.get('phone') or raw_data.get('value', '')
        formatted['value'] = phone
        formatted['name'] = phone
        
        # Parse phone components
        formatted['formatted'] = phone
        formatted['country_code'] = self._extract_country_code(phone)
        
        # Breach status
        if 'breach_count' in raw_data:
            formatted['breach_status'] = 'compromised'
            formatted['breach_count'] = raw_data.get('breach_count', 0)
        
        # Associated accounts
        formatted['associated_emails'] = raw_data.get('emails', [])
        formatted['associated_usernames'] = raw_data.get('usernames', [])
        
        return formatted
    
    def _format_username(self, template: Dict, raw_data: Dict) -> Dict:
        """Format username entity with template"""
        formatted = template.copy()
        
        username = raw_data.get('username') or raw_data.get('value', '')
        formatted['value'] = username
        formatted['name'] = username
        
        # Platform detection
        formatted['platforms'] = raw_data.get('platforms', [])
        
        # Breach information
        if 'breach_count' in raw_data:
            formatted['breach_status'] = 'compromised'
            formatted['breach_count'] = raw_data.get('breach_count', 0)
            formatted['breach_sources'] = raw_data.get('breach_sources', [])
        
        # Associated data
        formatted['associated_emails'] = raw_data.get('emails', [])
        formatted['associated_phones'] = raw_data.get('phones', [])
        
        return formatted
    
    def _format_url(self, template: Dict, raw_data: Dict) -> Dict:
        """Format URL/domain entity with template"""
        formatted = template.copy()
        
        domain = raw_data.get('domain') or raw_data.get('value', '')
        formatted['value'] = domain
        formatted['name'] = domain
        formatted['full_url'] = f"https://{domain}" if not domain.startswith('http') else domain
        
        # WHOIS data
        if 'registrant' in raw_data:
            reg = raw_data['registrant']
            formatted['registrant_name'] = reg.get('name')
            formatted['registrant_org'] = reg.get('organization')
            formatted['registrant_email'] = reg.get('email')
            formatted['registrant_phone'] = reg.get('phone')
            formatted['registrant_address'] = reg.get('address')
        
        formatted['created_date'] = raw_data.get('created')
        formatted['expires_date'] = raw_data.get('expires')
        formatted['nameservers'] = raw_data.get('nameservers', [])
        
        return formatted
    
    def _format_ip(self, template: Dict, raw_data: Dict) -> Dict:
        """Format IP address entity with template"""
        formatted = template.copy()
        
        ip = raw_data.get('ip') or raw_data.get('value', '')
        formatted['value'] = ip
        formatted['name'] = ip
        formatted['ip_version'] = 'IPv6' if ':' in ip else 'IPv4'
        
        # Associated domains
        formatted['associated_domains'] = raw_data.get('domains', [])
        
        # Geolocation if available
        if 'location' in raw_data:
            formatted['geolocation'] = raw_data['location']
        
        return formatted
    
    def _generic_populate(self, template: Dict, raw_data: Dict) -> Dict:
        """Generic template population for unknown types"""
        formatted = template.copy()
        
        # Try to map common fields
        formatted['value'] = raw_data.get('value', '')
        formatted['name'] = raw_data.get('name', formatted['value'])
        
        # Copy all data to 'about' section
        formatted['about'] = raw_data
        
        return formatted
    
    def _generic_format(self, entity_type: str, raw_data: Dict) -> Dict:
        """Generic format when no template exists"""
        return {
            'entity_type': entity_type,
            'value': raw_data.get('value', ''),
            'name': raw_data.get('name', ''),
            'data': raw_data,
            'created_at': datetime.utcnow().isoformat() + 'Z'
        }
    
    def _generate_node_id(self, entity_type: str, value: str) -> str:
        """Generate unique node ID for entity"""
        hash_input = f"{entity_type}:{value.lower()}"
        hash_val = hashlib.md5(hash_input.encode()).hexdigest()[:8]
        return f"node_entity_{entity_type}_{hash_val}"
    
    def _extract_sources(self, raw_data: Dict) -> List[str]:
        """Extract data sources from raw results"""
        sources = []
        
        # Check for explicit sources
        if 'sources_checked' in raw_data:
            sources.extend(raw_data['sources_checked'])
        
        # Check for API indicators
        if 'dehashed' in str(raw_data).lower():
            sources.append('DeHashed')
        if 'rocketreach' in str(raw_data).lower():
            sources.append('RocketReach')
        if 'whoisxml' in str(raw_data).lower():
            sources.append('WhoisXML')
        if 'osint' in str(raw_data).lower():
            sources.append('OSINT Industries')
        if 'opencorporates' in str(raw_data).lower():
            sources.append('OpenCorporates')
        if 'aleph' in str(raw_data).lower():
            sources.append('OCCRP Aleph')
        
        return list(set(sources))
    
    def _extract_country_code(self, phone: str) -> str:
        """Extract country code from phone number"""
        if phone.startswith('+1'):
            return '+1'
        elif phone.startswith('+44'):
            return '+44'
        elif phone.startswith('+'):
            # Extract up to 3 digits after +
            import re
            match = re.match(r'\+(\d{1,3})', phone)
            if match:
                return '+' + match.group(1)
        return ''
    
    def save_entity(self, entity_type: str, formatted_data: Dict, filename: Optional[str] = None) -> Path:
        """
        Save formatted entity to JSON file AND SQL database
        
        Returns:
            Path to saved file
        """
        # Save to SQL database FIRST (with deduplication)
        if self.save_to_db:
            node_id, was_merged = self.graph_db.save_entity(formatted_data)
            if was_merged:
                print(f"🔄 Merged with existing {entity_type} in database: {formatted_data.get('value')}")
            else:
                print(f"✨ Added new {entity_type} to database: {formatted_data.get('value')}")
            
            # Save relationships from template data
            if 'about' in formatted_data:
                self._save_relationships_to_db(node_id, formatted_data['about'])
        
        # Create entity type subdirectory
        type_dir = self.output_dir / entity_type
        type_dir.mkdir(exist_ok=True)
        
        # Generate filename if not provided
        if not filename:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            value_slug = formatted_data.get('value', 'unknown')[:30]
            value_slug = "".join(c for c in value_slug if c.isalnum() or c in '-_')
            filename = f"{entity_type}_{value_slug}_{timestamp}.json"
        
        # Save to file
        filepath = type_dir / filename
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(formatted_data, f, indent=2, ensure_ascii=False)
        
        print(f"📁 Saved {entity_type} entity to file: {filepath}")
        
        # Add to session tracking
        self.session_entities.append(formatted_data)
        
        return filepath
    
    def save_search_results(self, search_query: str, results: Dict) -> Dict[str, Path]:
        """
        Process and save all entities from a search result
        
        Args:
            search_query: The original search query
            results: Raw results from entity search tools
            
        Returns:
            Dict mapping entity types to saved file paths
        """
        saved_files = {}
        
        # Detect entity type from results
        if 'email' in results:
            entity_type = 'email'
            value = results['email']
        elif 'username' in results:
            entity_type = 'username'
            value = results['username']
        elif 'phone' in results:
            entity_type = 'phone'
            value = results['phone']
        elif 'domain' in results:
            entity_type = 'url'
            value = results['domain']
        elif 'name' in results and 'professional_data' in results:
            entity_type = 'person'
            value = results['name']
        elif 'name' in results and ('unified' in results or 'oc' in results):
            entity_type = 'company'
            value = results['name']
        else:
            # Try to detect from search query
            from wikiman_entity_autodetect import detect_entities
            entities = detect_entities(search_query)
            if entities:
                entity_type = entities[0][0]
                value = entities[0][1]
            else:
                entity_type = 'unknown'
                value = search_query
        
        # Format with template
        formatted = self.format_entity_result(
            entity_type=entity_type,
            raw_data=results,
            search_context={'query': search_query}
        )
        
        # Save main entity
        main_file = self.save_entity(entity_type, formatted)
        saved_files[entity_type] = main_file
        
        # Save related entities if present
        if 'results' in results and isinstance(results['results'], dict):
            for key, data in results['results'].items():
                if ':' in key:
                    sub_type, sub_value = key.split(':', 1)
                    sub_formatted = self.format_entity_result(
                        entity_type=sub_type,
                        raw_data=data,
                        search_context={'parent_query': search_query}
                    )
                    sub_file = self.save_entity(sub_type, sub_formatted)
                    saved_files[f"{sub_type}:{sub_value}"] = sub_file
        
        # Create session summary
        self._save_session_summary(search_query, saved_files)
        
        return saved_files
    
    def _save_session_summary(self, query: str, saved_files: Dict[str, Path]):
        """Save a summary of the session's entities and relationships"""
        summary = {
            'session_id': datetime.now().strftime('%Y%m%d_%H%M%S'),
            'query': query,
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'entities_saved': len(saved_files),
            'files': {k: str(v) for k, v in saved_files.items()},
            'entity_graph': {
                'nodes': len(self.session_entities),
                'entities': [
                    {
                        'type': e.get('_metadata', {}).get('entity_type'),
                        'value': e.get('value'),
                        'node_id': e.get('node_id')
                    }
                    for e in self.session_entities
                ]
            }
        }
        
        # Add database statistics if using DB
        if self.save_to_db:
            db_stats = self.graph_db.get_statistics()
            summary['database_stats'] = {
                'total_nodes': db_stats['total_nodes'],
                'total_edges': db_stats['total_edges'],
                'node_types': db_stats['node_types']
            }
            print(f"\n📊 Graph Database Status:")
            print(f"   Total Nodes: {db_stats['total_nodes']}")
            print(f"   Total Edges: {db_stats['total_edges']}")
        
        summary_file = self.output_dir / f"session_summary_{summary['session_id']}.json"
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2)
        
        print(f"📊 Session summary saved to: {summary_file}")
    
    def _save_relationships_to_db(self, source_node_id: str, about_data: Dict):
        """Save relationships from template data to database"""
        if not self.save_to_db:
            return
        
        relationship_fields = [
            'domain_relationships',
            'online_account_relationships', 
            'social_media_relationships',
            'mention_relationships',
            'password_breaches'
        ]
        
        for field in relationship_fields:
            if field in about_data and isinstance(about_data[field], list):
                for rel in about_data[field]:
                    # Create target node
                    target_value = rel.get('target_value', '')
                    target_type = rel.get('target_node_type', 'url')
                    target_class = rel.get('target_node_class', 'source')
                    
                    target_entity = {
                        'node_id': rel.get('target_node_id'),
                        'node_class': target_class,
                        'type': target_type,
                        'value': target_value,
                        'name': target_value,
                        '_metadata': {'entity_type': target_type}
                    }
                    
                    target_id, _ = self.graph_db.save_entity(target_entity)
                    
                    # Create edge
                    self.graph_db.save_edge(
                        source_node_id,
                        target_id,
                        rel.get('relationship_type', field.replace('_relationships', '')),
                        rel.get('context'),
                        rel.get('metadata'),
                        rel.get('confidence', 0.8)
                    )
    
    def get_template_fields(self, entity_type: str) -> List[str]:
        """Get list of fields for an entity type from its template"""
        template = self.templates.get(entity_type, {})
        
        # Extract all field names from template
        fields = []
        
        def extract_fields(obj, prefix=''):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    if key.startswith('_'):
                        continue
                    full_key = f"{prefix}.{key}" if prefix else key
                    fields.append(full_key)
                    if isinstance(value, dict):
                        extract_fields(value, full_key)
        
        extract_fields(template)
        return fields


# Convenience functions for WikiMan integration

def format_and_save_entity(entity_type: str, raw_results: Dict, query: str = None) -> Path:
    """Quick function to format and save an entity result"""
    formatter = WikiManTemplateFormatter()
    
    formatted = formatter.format_entity_result(
        entity_type=entity_type,
        raw_data=raw_results,
        search_context={'query': query} if query else None
    )
    
    return formatter.save_entity(entity_type, formatted)


def process_wikiman_search(query: str, search_results: Dict) -> Dict[str, Path]:
    """Process WikiMan search results and save all entities"""
    formatter = WikiManTemplateFormatter()
    return formatter.save_search_results(query, search_results)


if __name__ == "__main__":
    # Test the formatter
    print("WikiMan Template Formatter Test")
    print("=" * 60)
    
    formatter = WikiManTemplateFormatter()
    
    print(f"\n✅ Loaded {len(formatter.templates)} entity templates")
    
    # Test with sample data
    sample_email_result = {
        'email': 'john.doe@example.com',
        'breach_count': 5,
        'breaches': [
            {'database_name': 'COLLECTION1', 'obtained_from': '2022-01-15'},
            {'database_name': 'ALIEN TXTBASE', 'obtained_from': '2021-06-20'}
        ],
        'professional_data': {
            'name': 'John Doe',
            'current_employer': 'TechCorp',
            'current_title': 'Senior Developer'
        }
    }
    
    print("\n📝 Testing email formatting...")
    formatted = formatter.format_entity_result('email', sample_email_result)
    print(f"Formatted entity has {len(formatted)} fields")
    
    saved_path = formatter.save_entity('email', formatted)
    print(f"\n✅ Test complete! Check output at: {saved_path}")