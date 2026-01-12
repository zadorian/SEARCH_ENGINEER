"""
EYE-D Phone Output Handler

Creates C1 graph nodes for phone entities with proper Legend code integration.
Uses codes.json schema for structured data instead of JSON comment stuffing.

Legend Codes Used:
- 2: phone (entity node)
- 188: person_social_profiles (dataset node)
- 189: person_phone_records (dataset node)
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


class PhoneOutputHandler:
    """
    Handles phone entity output with Legend-compliant schema.

    Creates:
    - Phone entity node (_code: 2)
    - Phone record nodes (_code: 189) with associated_phone edges
    - Social profile nodes (_code: 188) with has_profile edges
    - Identity graph edges (_code: 190) for related entities
    """

    def __init__(self):
        self.results_root = Path(__file__).resolve().parent.parent / 'results' / 'phone'
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
        Process phone entity and create graph nodes.

        Returns the primary phone node with embedded edges to related nodes.
        Also creates secondary nodes (phone records, social profiles) as needed.
        """
        node_id = self._generate_id('phone', value)
        edges = []
        secondary_nodes = []

        if raw_data:
            source = raw_data.get('source_name') or raw_data.get('module') or 'unknown'

            # --- Legend 189: Phone Record ---
            if raw_data.get('carrier') or raw_data.get('line_type') or raw_data.get('location'):
                phone_record = self._create_phone_record_node(value, source, raw_data)
                secondary_nodes.append(phone_record)
                edges.append({
                    "target_id": phone_record['id'],
                    "relation": "associated_phone",  # Legend 189 edge_type
                    "_code": 189,
                    "verification_status": "VERIFIED",
                    "connection_reason": "phone_lookup"
                })

            # --- Legend 188: Social Profile ---
            if raw_data.get('profile_url'):
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

        # Provenance edges
        provenance_edges = self._create_provenance_edges(context)
        edges.extend(provenance_edges)

        # --- Primary Phone Node (Legend 2) ---
        node = {
            "id": node_id,
            "node_class": "ENTITY",
            "type": "phone",
            "_code": 2,
            "canonicalValue": value.strip(),
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

    def _create_phone_record_node(self, phone: str, source: str, raw_data: Dict) -> Dict:
        """
        Create a phone record node (Legend 189).

        Fields per codes.json: phone, carrier, line_type, country
        """
        record_id = self._generate_id('phone_record', f"{phone}:{source}")

        return {
            "id": record_id,
            "node_class": "DATASET",
            "type": "phone_record",
            "_code": 189,
            "canonicalValue": phone,
            "label": f"Phone Record: {phone}",
            # Legend 189 fields
            "phone": phone,
            "carrier": raw_data.get('carrier'),
            "line_type": raw_data.get('line_type'),
            "country": raw_data.get('location') or raw_data.get('country'),
            # Metadata
            "embedded_edges": [],
            "metadata": {
                "aggregator": source,
                "raw_data": raw_data
            },
            "createdAt": datetime.utcnow().isoformat()
        }

    def _create_social_profile_node(self, phone: str, source: str, raw_data: Dict) -> Dict:
        """
        Create a social profile node (Legend 188).

        Fields per codes.json: platform, username, url, followers, verified
        """
        username = raw_data.get('username', '')
        profile_id = self._generate_id('profile', f"{source}:{username or phone}")

        return {
            "id": profile_id,
            "node_class": "DATASET",
            "type": "social_profile",
            "_code": 188,
            "canonicalValue": f"{source}:{username}".lower(),
            "label": f"{source}: {username or phone}",
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

    def _create_identity_edges(self, phone: str, raw_data: Dict) -> List[Dict]:
        """
        Create identity graph edges (Legend 190).

        Links phone to related identity fragments: email, person name.
        """
        edges = []

        # Linked Email
        if raw_data.get('email'):
            email_val = raw_data['email']
            if isinstance(email_val, list):
                email_val = email_val[0]
            email_id = self._generate_id('email', email_val)
            edges.append({
                "target_id": email_id,
                "relation": "related_to",
                "_code": 190,
                "verification_status": "VERIFIED",
                "connection_reason": "same_record"
            })

        # Linked Person Name
        if raw_data.get('name'):
            name_val = raw_data['name']
            person_id = self._generate_id('person', name_val)
            edges.append({
                "target_id": person_id,
                "relation": "has_phone",
                "_code": 190,
                "verification_status": "VERIFIED",
                "connection_reason": "same_record"
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
