"""
SOCIALITE Person Name Output Handler

Creates C1 graph nodes for person entities with proper embedded edges.
Pushes to cymonides-1 with VERIFIED/UNVERIFIED status.

Legend Codes Used:
- 7: person_name (entity node)
- 188: person_social_profiles (profile node)
- 190: person_identity_graph (edges)
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


class PersonNameOutputHandler:
    """
    Handles person name entity output with C1-compliant schema.

    Creates:
    - Person entity node (_code: 7)
    - Profile nodes (_code: 188) with has_profile edges
    - Company edges with works_at relationship
    - Connection edges with connected_to relationship
    """

    def __init__(self):
        self.results_root = Path(__file__).resolve().parent.parent / 'results' / 'person_name'
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
        Process person name entity and create graph nodes.

        Returns the primary person node with embedded edges to related nodes.
        """
        node_id = self._generate_id('person', value)
        edges = []
        secondary_nodes = []

        if raw_data:
            source = raw_data.get('source_name') or raw_data.get('module') or 'unknown'

            # --- Edge: person has_profile (various platforms) ---
            profile_urls = self._extract_profile_urls(raw_data)
            for platform, url in profile_urls:
                profile_node = self._create_profile_node(
                    platform=platform,
                    person_name=value,
                    profile_url=url,
                    raw_data=raw_data
                )
                secondary_nodes.append(profile_node)
                edges.append({
                    "target_id": profile_node['id'],
                    "relation": "has_profile",
                    "_code": 188,
                    "verification_status": "UNVERIFIED",  # Name match is not definitive
                    "connection_reason": "name_match",
                    "query_sequence_tag": f"{value}_1"
                })

            # --- Edge: person works_at company ---
            companies = self._extract_companies(raw_data)
            for company_name in companies:
                company_id = self._generate_id('company', company_name)
                edges.append({
                    "target_id": company_id,
                    "relation": "works_at",
                    "_code": 8,
                    "verification_status": "VERIFIED",
                    "connection_reason": "employment_record"
                })

            # --- Edge: person connected_to person ---
            connections = self._extract_connections(raw_data)
            for connected_name in connections:
                connected_id = self._generate_id('person', connected_name)
                edges.append({
                    "target_id": connected_id,
                    "relation": "connected_to",
                    "_code": 190,
                    "verification_status": "VERIFIED",
                    "connection_reason": "social_connection"
                })

            # --- Direct Entity Linking (Identity Graph) ---
            # Linked Emails
            emails = raw_data.get('emails', raw_data.get('email', []))
            if isinstance(emails, str):
                emails = [emails]
            for email in emails[:5]:  # Limit to 5
                email_id = self._generate_id('email', email)
                edges.append({
                    "target_id": email_id,
                    "relation": "related_to",
                    "_code": 190,
                    "verification_status": "VERIFIED",
                    "connection_reason": "profile_email"
                })

            # Linked Phone
            phones = raw_data.get('phones', raw_data.get('phone', []))
            if isinstance(phones, str):
                phones = [phones]
            for phone in phones[:3]:  # Limit to 3
                phone_id = self._generate_id('phone', phone)
                edges.append({
                    "target_id": phone_id,
                    "relation": "related_to",
                    "_code": 190,
                    "verification_status": "VERIFIED",
                    "connection_reason": "profile_phone"
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
            structured_data['identity_graph'] = {
                "_code": 190,
                "seed_identifier": value,
                "linked_emails": raw_data.get('emails', []),
                "linked_phones": raw_data.get('phones', []),
                "linked_companies": self._extract_companies(raw_data),
                "linked_profiles": [url for _, url in self._extract_profile_urls(raw_data)]
            }

        comment_payload = json.dumps(structured_data, indent=2, ensure_ascii=False) if structured_data else None

        # --- Primary Person Node (Legend 7) ---
        node = {
            "id": node_id,
            "node_class": "SUBJECT",
            "type": "person",
            "_code": 7,
            "canonicalValue": value.lower().strip(),
            "label": value,
            "value": value,
            "comment": comment_payload,
            "embedded_edges": edges,
            "projectId": context.get('project_id'),
            "metadata": context.get('metadata', {}),
            "createdAt": datetime.utcnow().isoformat(),
            "updatedAt": datetime.utcnow().isoformat(),
            "lastSeen": datetime.utcnow().isoformat()
        }

        # Save all nodes
        self._save(node)
        for secondary in secondary_nodes:
            self._save(secondary)

        return node

    def _extract_profile_urls(self, raw_data: Dict) -> List[tuple]:
        """Extract profile URLs and their platforms from raw data."""
        profiles = []

        # Direct URL fields
        url_fields = {
            'linkedin_url': 'linkedin',
            'facebook_url': 'facebook',
            'twitter_url': 'twitter',
            'instagram_url': 'instagram',
            'threads_url': 'threads',
            'tiktok_url': 'tiktok',
            'profile_url': raw_data.get('platform', 'unknown')
        }

        for field, platform in url_fields.items():
            if raw_data.get(field):
                profiles.append((platform, raw_data[field]))

        # Social profiles array
        for profile in raw_data.get('social_profiles', []):
            if isinstance(profile, dict):
                profiles.append((
                    profile.get('platform', 'unknown'),
                    profile.get('url', profile.get('profile_url', ''))
                ))
            elif isinstance(profile, str):
                profiles.append(('unknown', profile))

        return profiles

    def _extract_companies(self, raw_data: Dict) -> List[str]:
        """Extract company names from raw data."""
        companies = []

        # Direct company field
        if raw_data.get('company'):
            companies.append(raw_data['company'])

        # Current company
        if raw_data.get('current_company'):
            companies.append(raw_data['current_company'])

        # Employment history
        for job in raw_data.get('employment', raw_data.get('experience', [])):
            if isinstance(job, dict) and job.get('company'):
                companies.append(job['company'])

        return list(set(companies))  # Dedupe

    def _extract_connections(self, raw_data: Dict) -> List[str]:
        """Extract connection names from raw data."""
        connections = []

        for conn in raw_data.get('connections', []):
            if isinstance(conn, dict):
                name = conn.get('name') or conn.get('full_name')
                if name:
                    connections.append(name)
            elif isinstance(conn, str):
                connections.append(conn)

        return connections[:20]  # Limit to 20

    def _create_profile_node(self, platform: str, person_name: str, profile_url: str, raw_data: Dict) -> Dict:
        """Create a social profile node (Legend 188)."""
        username = raw_data.get('username', '')
        profile_id = self._generate_id('profile', f"{platform}:{username or person_name}")

        return {
            "id": profile_id,
            "node_class": "SUBJECT",
            "type": "profile",
            "_code": 188,
            "canonicalValue": f"{platform}:{username or person_name}".lower(),
            "label": f"{person_name} ({platform})",
            "value": profile_url,
            "platform": platform,
            "username": username,
            "url": profile_url,
            "embedded_edges": [],
            "metadata": {"person_name": person_name},
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


__all__ = ['PersonNameOutputHandler']
