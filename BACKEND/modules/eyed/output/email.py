"""
EYE-D Email Output Handler

Creates C1 graph nodes for email entities with proper Legend code integration.
Uses codes.json schema for structured data instead of JSON comment stuffing.

Legend Codes Used:
- 1: email (entity node)
- 187: person_email_breaches (dataset node)
- 188: person_social_profiles (dataset node)
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


class EmailOutputHandler:
    """
    Handles email entity output with Legend-compliant schema.

    Creates:
    - Email entity node (_code: 1)
    - Breach record nodes (_code: 187) with exposed_in edges
    - Social profile nodes (_code: 188) with has_profile edges
    - Identity graph edges (_code: 190) for related entities
    """

    def __init__(self):
        self.results_root = Path(__file__).resolve().parent.parent / 'results' / 'email'
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
        Process email entity and create graph nodes.

        Returns the primary email node with embedded edges to related nodes.
        Also creates secondary nodes (breach records, social profiles) as needed.
        """
        node_id = self._generate_id('email', value)
        edges = []
        secondary_nodes = []  # Nodes created for breach records, social profiles, etc.

        if raw_data:
            source = raw_data.get('source_name') or raw_data.get('module') or 'unknown'

            # --- Legend 187: Breach Data ---
            if self._is_breach_data(source, raw_data):
                breach_node = self._create_breach_node(value, source, raw_data)
                secondary_nodes.append(breach_node)
                edges.append({
                    "target_id": breach_node['id'],
                    "relation": "exposed_in",  # Legend 187 edge_type
                    "_code": 187,
                    "verification_status": "VERIFIED",
                    "connection_reason": "breach_exposure"
                })

            # --- Legend 188: Social Profile ---
            elif self._is_social_profile(raw_data):
                profile_node = self._create_social_profile_node(value, source, raw_data)
                secondary_nodes.append(profile_node)
                edges.append({
                    "target_id": profile_node['id'],
                    "relation": "has_profile",  # Legend 188 edge_type
                    "_code": 188,
                    "verification_status": "VERIFIED",
                    "connection_reason": "profile_association"
                })

            # --- Legend 190: Identity Graph Edges ---
            identity_edges = self._create_identity_edges(value, raw_data)
            edges.extend(identity_edges)

        # Domain inference edge (email → domain)
        if '@' in value:
            domain = value.split('@')[1]
            domain_id = self._generate_id('domain', domain)
            edges.append({
                "target_id": domain_id,
                "relation": "part_of",
                "verification_status": "VERIFIED",
                "connection_reason": "domain_inference"
            })

        # Provenance edges (aggregator links)
        provenance_edges = self._create_provenance_edges(context)
        edges.extend(provenance_edges)

        # --- Primary Email Node (Legend 1) ---
        node = {
            "id": node_id,
            "node_class": "ENTITY",
            "type": "email",
            "_code": 1,
            "canonicalValue": value.lower().strip(),
            "label": value,
            "value": value,
            "embedded_edges": edges,
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

    def _is_breach_data(self, source: str, raw_data: Dict) -> bool:
        """Check if raw_data represents breach exposure."""
        breach_indicators = ['dehashed', 'hibp', 'breach', 'leak']
        source_lower = source.lower()
        return (
            any(ind in source_lower for ind in breach_indicators) or
            raw_data.get('password') or
            raw_data.get('hashed_password') or
            raw_data.get('database_name')
        )

    def _is_social_profile(self, raw_data: Dict) -> bool:
        """Check if raw_data represents a social profile."""
        return bool(raw_data.get('profile_url') or raw_data.get('username'))

    def _create_breach_node(self, email: str, source: str, raw_data: Dict) -> Dict:
        """
        Create a breach record node (Legend 187).

        Fields per codes.json: source, breach, breached_at, compromised_fields, password_exposed
        """
        breach_id = self._generate_id('breach', f"{email}:{raw_data.get('database_name', source)}")

        return {
            "id": breach_id,
            "node_class": "DATASET",
            "type": "breach_record",
            "_code": 187,
            "canonicalValue": f"{email}@{raw_data.get('database_name', 'unknown')}",
            "label": f"Breach: {raw_data.get('database_name', source)}",
            # Legend 187 fields
            "source": source,
            "breach": raw_data.get('database_name', 'Unknown'),
            "breached_at": raw_data.get('breach_date'),
            "compromised_fields": [k for k in raw_data.keys() if raw_data[k]],
            "password_exposed": bool(raw_data.get('password')),
            # Metadata
            "embedded_edges": [],
            "metadata": {
                "aggregator": source,
                "raw_data": raw_data
            },
            "createdAt": datetime.utcnow().isoformat()
        }

    def _create_social_profile_node(self, email: str, source: str, raw_data: Dict) -> Dict:
        """
        Create a social profile node (Legend 188).

        Fields per codes.json: platform, username, url, followers, verified
        """
        username = raw_data.get('username', '')
        profile_id = self._generate_id('profile', f"{source}:{username or email}")

        return {
            "id": profile_id,
            "node_class": "DATASET",
            "type": "social_profile",
            "_code": 188,
            "canonicalValue": f"{source}:{username}".lower(),
            "label": f"{source}: {username or email}",
            # Legend 188 fields
            "platform": source,
            "username": username,
            "url": raw_data.get('profile_url', ''),
            "followers": raw_data.get('followers'),
            "verified": raw_data.get('verified', False),
            # Metadata
            "embedded_edges": [],
            "metadata": {
                "raw_data": raw_data
            },
            "createdAt": datetime.utcnow().isoformat()
        }

    def _create_identity_edges(self, email: str, raw_data: Dict) -> List[Dict]:
        """
        Create identity graph edges (Legend 190).

        Links email to related identity fragments: phone, username, password.
        """
        edges = []

        # Linked Password
        if raw_data.get('password'):
            pwd_id = self._generate_id('password', raw_data['password'])
            edges.append({
                "target_id": pwd_id,
                "relation": "exposed_password",
                "_code": 190,
                "verification_status": "VERIFIED",
                "connection_reason": "breach_link"
            })

        # Linked Phone
        if raw_data.get('phone'):
            phone_val = raw_data['phone']
            if isinstance(phone_val, list):
                phone_val = phone_val[0]
            phone_id = self._generate_id('phone', phone_val)
            edges.append({
                "target_id": phone_id,
                "relation": "related_to",
                "_code": 190,
                "verification_status": "VERIFIED",
                "connection_reason": "breach_link"
            })

        # Linked Username
        if raw_data.get('username'):
            user_val = raw_data['username']
            if isinstance(user_val, list):
                user_val = user_val[0]
            user_id = self._generate_id('username', user_val)
            edges.append({
                "target_id": user_id,
                "relation": "related_to",
                "_code": 190,
                "verification_status": "VERIFIED",
                "connection_reason": "breach_link"
            })

        return edges

    def _create_provenance_edges(self, context: Dict) -> List[Dict]:
        """Create edges linking to aggregator/input sources."""
        edges = []
        agg_ids = context.get('aggregator_ids', [])
        if context.get('aggregator_id'):
            agg_ids.append(context['aggregator_id'])

        relation = "input_of" if context.get('is_input') else "output_of"

        for agg_id in agg_ids:
            edges.append({
                "target_id": agg_id,
                "relation": relation,
                "verification_status": "VERIFIED" if context.get('is_input') else "UNVERIFIED",
                "connection_reason": "aggregator_link"
            })

        return edges

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
