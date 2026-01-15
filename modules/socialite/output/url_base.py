"""
SOCIALITE Base URL Output Handler

Base class for all platform-specific URL handlers.
Provides common functionality for creating C1 nodes from social media URLs.
"""

import json
import os
import hashlib
import time
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from abc import ABC, abstractmethod

try:
    from elasticsearch import Elasticsearch
    ES_AVAILABLE = True
except ImportError:
    ES_AVAILABLE = False


class UrlOutputHandler(ABC):
    """
    Base class for URL output handlers.

    Each platform handler inherits from this and implements:
    - platform: The platform name (facebook, instagram, etc.)
    - _code: The Legend code for this URL type
    - extract_username: Extract username from URL
    """

    def __init__(self):
        self.results_root = Path(__file__).resolve().parent.parent / 'results' / 'url'
        self.results_root.mkdir(parents=True, exist_ok=True)
        self.es = None
        if ES_AVAILABLE:
            es_host = os.getenv("ELASTICSEARCH_HOST", "http://localhost:9200")
            self.es_index = os.getenv("CYMONIDES_1_INDEX", "cymonides-1")
            try:
                self.es = Elasticsearch([es_host])
            except Exception:
                self.es = None

    @property
    @abstractmethod
    def platform(self) -> str:
        """Platform name (facebook, instagram, twitter, etc.)"""
        pass

    @property
    @abstractmethod
    def _code(self) -> int:
        """Legend code for this URL type."""
        pass

    @abstractmethod
    def extract_username(self, url: str) -> Optional[str]:
        """Extract username from the URL."""
        pass

    def process(self, value: str, context: Dict[str, Any], raw_data: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Process URL entity and create graph nodes.

        Returns the primary URL node with embedded edges to related nodes.
        """
        node_id = self._generate_id(f'{self.platform}_url', value)
        edges = []
        secondary_nodes = []

        # Extract username from URL
        username = self.extract_username(value)

        # --- Edge: URL contains profile ---
        if username:
            profile_node = self._create_profile_node(
                username=username,
                profile_url=value,
                raw_data=raw_data
            )
            secondary_nodes.append(profile_node)
            edges.append({
                "target_id": profile_node['id'],
                "relation": "contains_profile",
                "_code": 188,
                "verification_status": "VERIFIED",
                "connection_reason": "url_profile"
            })

            # Also create username node
            username_id = self._generate_id('username', username)
            edges.append({
                "target_id": username_id,
                "relation": "identifies",
                "_code": 3,
                "verification_status": "VERIFIED",
                "connection_reason": "url_username_extraction"
            })

        # --- Edge: URL belongs to platform ---
        platform_id = self._generate_id('platform', self.platform)
        edges.append({
            "target_id": platform_id,
            "relation": "hosted_on",
            "_code": 100,
            "verification_status": "VERIFIED",
            "connection_reason": "platform_association"
        })

        # --- Extract additional data from raw_data ---
        if raw_data:
            # Person name from profile
            person_name = raw_data.get('name') or raw_data.get('full_name')
            if person_name:
                person_id = self._generate_id('person', person_name)
                edges.append({
                    "target_id": person_id,
                    "relation": "belongs_to",
                    "_code": 7,
                    "verification_status": "VERIFIED",
                    "connection_reason": "profile_owner"
                })

            # Posts from this profile
            for post in raw_data.get('posts', [])[:10]:
                post_id = self._generate_id('post', post.get('id', post.get('url', '')))
                edges.append({
                    "target_id": post_id,
                    "relation": "contains_post",
                    "_code": 200,
                    "verification_status": "VERIFIED",
                    "connection_reason": "content_source"
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
        structured_data = {
            "url_data": {
                "_code": self._code,
                "platform": self.platform,
                "url": value,
                "username": username,
                "raw": raw_data if raw_data else {}
            }
        }

        comment_payload = json.dumps(structured_data, indent=2, ensure_ascii=False)

        # --- Primary URL Node ---
        node = {
            "id": node_id,
            "node_class": "LOCATION",
            "type": f"{self.platform}_url",
            "_code": self._code,
            "canonicalValue": value.lower().strip(),
            "label": f"{self.platform.title()}: {username or value}",
            "value": value,
            "comment": comment_payload,
            "embedded_edges": edges,
            "projectId": context.get('project_id'),
            "metadata": {
                "platform": self.platform,
                "username": username,
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

    def _create_profile_node(self, username: str, profile_url: str, raw_data: Dict) -> Dict:
        """Create a profile node from URL."""
        profile_id = self._generate_id('profile', f"{self.platform}:{username}")

        return {
            "id": profile_id,
            "node_class": "SUBJECT",
            "type": "profile",
            "_code": 188,
            "canonicalValue": f"{self.platform}:{username}".lower(),
            "label": f"{username} ({self.platform})",
            "value": profile_url,
            "platform": self.platform,
            "username": username,
            "url": profile_url,
            "followers": raw_data.get('followers') if raw_data else None,
            "verified": raw_data.get('verified', False) if raw_data else False,
            "embedded_edges": [],
            "metadata": {"raw_data": raw_data} if raw_data else {},
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


__all__ = ['UrlOutputHandler']
