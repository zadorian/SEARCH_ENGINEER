"""
SOCIALITE Username Output Handler

Creates C1 graph nodes for username entities with proper embedded edges.
Pushes to cymonides-1 with VERIFIED/UNVERIFIED status.

Legend Codes Used:
- 3: username (entity node)
- 188: person_social_profiles (profile node)
- 100: platform (platform node)
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


class UsernameOutputHandler:
    """
    Handles username entity output with C1-compliant schema.

    Creates:
    - Username entity node (_code: 3)
    - Platform nodes (_code: 100) with has_account_on edges
    - Profile nodes (_code: 188) with finds edges
    """

    def __init__(self):
        self.results_root = Path(__file__).resolve().parent.parent / 'results' / 'username'
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
        Process username entity and create graph nodes.

        Returns the primary username node with embedded edges to related nodes.
        """
        node_id = self._generate_id('username', value)
        edges = []
        secondary_nodes = []

        platform_name = None
        profile_url = None

        if raw_data:
            # Extract platform information
            platform_name = (
                raw_data.get('module') or
                raw_data.get('site') or
                raw_data.get('site_name') or
                raw_data.get('platform')
            )
            profile_url = raw_data.get('profile_url') or raw_data.get('url')

            # --- Edge: username finds profile ---
            if profile_url:
                profile_node = self._create_profile_node(
                    platform=platform_name or 'unknown',
                    username=value,
                    profile_url=profile_url,
                    raw_data=raw_data
                )
                secondary_nodes.append(profile_node)
                edges.append({
                    "target_id": profile_node['id'],
                    "relation": "finds",
                    "_code": 188,
                    "verification_status": "VERIFIED",
                    "connection_reason": "direct_match"
                })

            # --- Edge: username has_account_on platform ---
            if platform_name:
                platform_id = self._generate_id('platform', platform_name)
                edges.append({
                    "target_id": platform_id,
                    "relation": "has_account_on",
                    "_code": 100,
                    "verification_status": "VERIFIED",
                    "connection_reason": "platform_association"
                })
                self._create_platform_node(platform_name, platform_id)

            # --- Direct Entity Linking ---
            # Linked Email
            if raw_data.get('email'):
                email_val = raw_data['email']
                if isinstance(email_val, list):
                    email_val = email_val[0]
                email_id = self._generate_id('email', email_val)
                edges.append({
                    "target_id": email_id,
                    "relation": "related_to",
                    "verification_status": "VERIFIED",
                    "connection_reason": "same_record"
                })

            # Linked Person Name
            if raw_data.get('name') or raw_data.get('full_name'):
                name_val = raw_data.get('name') or raw_data.get('full_name')
                person_id = self._generate_id('person', name_val)
                edges.append({
                    "target_id": person_id,
                    "relation": "related_to",
                    "verification_status": "VERIFIED",
                    "connection_reason": "profile_name"
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
            structured_data['social_profile'] = {
                "_code": 188,
                "platform": platform_name or 'unknown',
                "username": value,
                "url": profile_url or '',
                "followers": raw_data.get('followers'),
                "verified": raw_data.get('verified', False),
                "bio": raw_data.get('bio', raw_data.get('description', '')),
                "raw": raw_data
            }

        comment_payload = json.dumps(structured_data, indent=2, ensure_ascii=False) if structured_data else None

        # --- Primary Username Node (Legend 3) ---
        node = {
            "id": node_id,
            "node_class": "SUBJECT",
            "type": "username",
            "_code": 3,
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

    def _create_profile_node(self, platform: str, username: str, profile_url: str, raw_data: Dict) -> Dict:
        """Create a social profile node (Legend 188)."""
        profile_id = self._generate_id('profile', f"{platform}:{username}")

        return {
            "id": profile_id,
            "node_class": "SUBJECT",
            "type": "profile",
            "_code": 188,
            "canonicalValue": f"{platform}:{username}".lower(),
            "label": f"{username} ({platform})",
            "value": profile_url,
            "platform": platform,
            "username": username,
            "url": profile_url,
            "followers": raw_data.get('followers'),
            "verified": raw_data.get('verified', False),
            "embedded_edges": [],
            "metadata": {"raw_data": raw_data},
            "createdAt": datetime.utcnow().isoformat()
        }

    def _create_platform_node(self, name: str, node_id: str):
        """Create a platform node (Legend 100)."""
        node = {
            "id": node_id,
            "node_class": "LOCATION",
            "type": "platform",
            "_code": 100,
            "canonicalValue": name.lower().strip(),
            "label": name.title(),
            "value": name,
            "embedded_edges": [],
            "metadata": {"type": "social_platform"},
            "createdAt": datetime.utcnow().isoformat()
        }
        if self.es:
            try:
                self.es.index(index=self.es_index, id=node_id, body=node)
            except:
                pass

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


__all__ = ['UsernameOutputHandler']
