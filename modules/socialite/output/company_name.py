"""
SOCIALITE Company Name Output Handler

Creates C1 graph nodes for company entities with proper embedded edges.
Pushes to cymonides-1 with VERIFIED/UNVERIFIED status.

Legend Codes Used:
- 8: company (entity node)
- 188: person_social_profiles (for company pages)
- 105: linkedin_url (company LinkedIn)
"""

import json
import os
import hashlib
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

try:
    from elasticsearch import Elasticsearch
    ES_AVAILABLE = True
except ImportError:
    ES_AVAILABLE = False


class CompanyNameOutputHandler:
    """
    Handles company entity output with C1-compliant schema.

    Creates:
    - Company entity node (_code: 8)
    - Employee edges with has_employee relationship
    - Company profile nodes for social pages
    """

    def __init__(self):
        self.results_root = Path(__file__).resolve().parent.parent / 'results' / 'company_name'
        self.results_root.mkdir(parents=True, exist_ok=True)
        self.es = None
        if ES_AVAILABLE:
            es_host = os.getenv("ELASTICSEARCH_HOST", "http://localhost:9200")
            self.es_index = os.getenv("CYMONIDES_1_INDEX", "cymonides-1")
            try:
                self.es = Elasticsearch([es_host])
            except Exception:
                self.es = None

    def process(self, value: str, context: Dict[str, Any], raw_data: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Process company entity and create graph nodes.

        Returns the primary company node with embedded edges to related nodes.
        """
        node_id = self._generate_id('company', value)
        edges = []
        secondary_nodes = []

        if raw_data:
            source = raw_data.get('source_name') or raw_data.get('module') or 'unknown'

            # --- Edge: company has_profile (LinkedIn, Facebook pages) ---
            profile_urls = self._extract_company_profiles(raw_data)
            for platform, url in profile_urls:
                profile_node = self._create_company_profile_node(
                    platform=platform,
                    company_name=value,
                    profile_url=url,
                    raw_data=raw_data
                )
                secondary_nodes.append(profile_node)
                edges.append({
                    "target_id": profile_node['id'],
                    "relation": "has_profile",
                    "_code": 188,
                    "verification_status": "VERIFIED",
                    "connection_reason": "company_page"
                })

            # --- Edge: company has_employee person ---
            employees = self._extract_employees(raw_data)
            for employee in employees:
                person_id = self._generate_id('person', employee['name'])
                edges.append({
                    "target_id": person_id,
                    "relation": "has_employee",
                    "_code": 7,
                    "verification_status": "VERIFIED",
                    "connection_reason": "employment_record",
                    "metadata": {
                        "title": employee.get('title', ''),
                        "department": employee.get('department', '')
                    }
                })

            # --- Direct Entity Linking ---
            # Company website domain
            if raw_data.get('website') or raw_data.get('domain'):
                domain = raw_data.get('website') or raw_data.get('domain')
                domain_id = self._generate_id('domain', domain)
                edges.append({
                    "target_id": domain_id,
                    "relation": "owns_domain",
                    "verification_status": "VERIFIED",
                    "connection_reason": "company_website"
                })

            # Company email domains
            for email_domain in raw_data.get('email_domains', []):
                domain_id = self._generate_id('domain', email_domain)
                edges.append({
                    "target_id": domain_id,
                    "relation": "owns_domain",
                    "verification_status": "VERIFIED",
                    "connection_reason": "email_domain"
                })

        # --- Aggregator/provenance edges ---
        agg_ids = context.get('aggregator_ids', [])
        if context.get('aggregator_id'):
            agg_ids.append(context['aggregator_id'])

        relation = "input_of" if context.get('is_input') else "output_of"
        verification = "VERIFIED" if context.get('is_input') else "UNVERIFIED"

        for agg_id in agg_ids:
            edge = {
                "target_id": agg_id,
                "relation": relation,
                "verification_status": verification,
                "connection_reason": "aggregator_link"
            }
            if verification == "UNVERIFIED":
                edge["query_sequence_tag"] = f"{value}_1"
            edges.append(edge)

        # Edge to input entity
        if context.get('input_id') and not context.get('is_input'):
            edges.append({
                "target_id": context['input_id'],
                "relation": "related_to",
                "verification_status": "UNVERIFIED",
                "connection_reason": "input_context",
                "query_sequence_tag": f"{context['input_id']}_1"
            })

        # --- Structured Data in comment ---
        structured_data = {}
        if raw_data:
            structured_data['company_data'] = {
                "_code": 8,
                "name": value,
                "industry": raw_data.get('industry'),
                "size": raw_data.get('company_size', raw_data.get('size')),
                "headquarters": raw_data.get('headquarters', raw_data.get('location')),
                "founded": raw_data.get('founded'),
                "website": raw_data.get('website'),
                "employee_count": len(self._extract_employees(raw_data)),
                "raw": raw_data
            }

        comment_payload = json.dumps(structured_data, indent=2, ensure_ascii=False) if structured_data else None

        # --- Primary Company Node (Legend 8) ---
        node = {
            "id": node_id,
            "node_class": "SUBJECT",
            "type": "company",
            "_code": 8,
            "canonicalValue": value.lower().strip(),
            "label": value,
            "value": value,
            "comment": comment_payload,
            "embedded_edges": edges,
            "projectId": context.get('project_id'),
            "metadata": {
                "industry": raw_data.get('industry') if raw_data else None,
                "size": raw_data.get('company_size') if raw_data else None,
                **context.get('metadata', {})
            },
            "createdAt": datetime.utcnow().isoformat(),
            "updatedAt": datetime.utcnow().isoformat(),
            "lastSeen": datetime.utcnow().isoformat()
        }

        # Save all nodes
        self._save(node)
        for secondary in secondary_nodes:
            self._save(secondary)

        return node

    def _extract_company_profiles(self, raw_data: Dict) -> List[tuple]:
        """Extract company profile URLs from raw data."""
        profiles = []

        url_fields = {
            'linkedin_url': 'linkedin',
            'facebook_url': 'facebook',
            'twitter_url': 'twitter',
            'company_page_url': raw_data.get('platform', 'unknown')
        }

        for field, platform in url_fields.items():
            if raw_data.get(field):
                profiles.append((platform, raw_data[field]))

        return profiles

    def _extract_employees(self, raw_data: Dict) -> List[Dict]:
        """Extract employee information from raw data."""
        employees = []

        # Employees array
        for emp in raw_data.get('employees', []):
            if isinstance(emp, dict):
                if emp.get('name') or emp.get('full_name'):
                    employees.append({
                        'name': emp.get('name') or emp.get('full_name'),
                        'title': emp.get('title', emp.get('position', '')),
                        'department': emp.get('department', '')
                    })
            elif isinstance(emp, str):
                employees.append({'name': emp, 'title': '', 'department': ''})

        # Officers/executives
        for officer in raw_data.get('officers', raw_data.get('executives', [])):
            if isinstance(officer, dict) and officer.get('name'):
                employees.append({
                    'name': officer['name'],
                    'title': officer.get('title', 'Executive'),
                    'department': ''
                })

        return employees[:50]  # Limit to 50

    def _create_company_profile_node(self, platform: str, company_name: str, profile_url: str, raw_data: Dict) -> Dict:
        """Create a company profile node."""
        profile_id = self._generate_id('profile', f"company:{platform}:{company_name}")

        return {
            "id": profile_id,
            "node_class": "SUBJECT",
            "type": "profile",
            "_code": 188,
            "canonicalValue": f"{platform}:company:{company_name}".lower(),
            "label": f"{company_name} ({platform})",
            "value": profile_url,
            "platform": platform,
            "url": profile_url,
            "embedded_edges": [],
            "metadata": {
                "company_name": company_name,
                "profile_type": "company"
            },
            "createdAt": datetime.utcnow().isoformat()
        }

    def _generate_id(self, type: str, value: str) -> str:
        """Generate deterministic node ID."""
        raw = f"{type}:{str(value).lower().strip()}"
        return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]

    def _save(self, node: Dict):
        """Save node to disk and Elasticsearch."""
        filename = f"{node['id']}_{int(time.time())}.json"
        file_path = self.results_root / filename
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(node, f, indent=2, ensure_ascii=False)
        if self.es:
            try:
                self.es.index(index=self.es_index, id=node['id'], body=node)
            except:
                pass


__all__ = ['CompanyNameOutputHandler']
