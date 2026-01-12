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

# Legend codes from /data/SEARCH_ENGINEER/BACKEND/modules/input_output/matrix/codes.json
# 3 = username, 188 = person_social_profiles

# --- Handler ---
class UsernameOutputHandler:
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
        node_id = self._generate_id('username', value)
        edges = []
        
        # --- Structured Data ---
        structured_data = {}
        platform_name = None
        
        if raw_data:
            platform_name = (
                raw_data.get('module') or 
                raw_data.get('site') or 
                raw_data.get('site_name') or 
                raw_data.get('database_name') or
                raw_data.get('platform')
            )
            
            # Social Profile - Legend 188: person_social_profiles
            structured_data['social_profile'] = {
                "_code": 188,
                "platform": platform_name or 'unknown',
                "username": value,
                "url": raw_data.get('profile_url') or raw_data.get('url') or '',
                "followers": raw_data.get('followers'),
                "verified": raw_data.get('verified', False),
                "raw": raw_data
            }

            # --- Direct Entity Linking ---
            # 1. Linked Email
            if raw_data.get('email'):
                email_val = raw_data['email']
                if isinstance(email_val, list): email_val = email_val[0]
                email_id = self._generate_id('email', email_val)
                edges.append({
                    "target_id": email_id,
                    "relation": "related_to",
                    "verification_status": "VERIFIED",
                    "connection_reason": "same_record"
                })

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

        if context.get('input_id') and not context.get('is_input'):
            edges.append({
                "target_id": context['input_id'],
                "relation": "related_to",
                "verification_status": "UNVERIFIED",
                "connection_reason": "input_context"
            })

        if platform_name:
            platform_id = self._generate_id('platform', platform_name)
            edges.append({
                "target_id": platform_id,
                "relation": "account_on",
                "verification_status": "VERIFIED",
                "connection_reason": "platform_association"
            })
            self._create_platform_node(platform_name, platform_id)

        comment_payload = None
        if structured_data:
            comment_payload = json.dumps(structured_data, indent=2, ensure_ascii=False)
        elif raw_data:
            comment_payload = json.dumps(raw_data, indent=2, ensure_ascii=False)

        node = {
            "id": node_id,
            "node_class": "ENTITY",
            "type": "username",
            "_code": 3,  # Legend 3: username
            "canonicalValue": value.lower().strip(),
            "label": value,
            "value": value,
            "comment": comment_payload,
            "embedded_edges": edges,
            "metadata": context.get('metadata', {}),
            "createdAt": datetime.utcnow().isoformat(),
            "updatedAt": datetime.utcnow().isoformat(),
            "lastSeen": datetime.utcnow().isoformat()
        }
        
        self._save(node)
        return node

    def _create_platform_node(self, name: str, node_id: str):
        node = {
            "id": node_id,
            "node_class": "LOCATION",
            "type": "platform",
            "canonicalValue": name.lower().strip(),
            "label": name,
            "value": name,
            "embedded_edges": [],
            "metadata": {"type": "social_platform_or_database"},
            "createdAt": datetime.utcnow().isoformat()
        }
        if self.es:
            try: self.es.index(index=self.es_index, id=node_id, body=node)
            except: pass

    def _generate_id(self, type: str, value: str) -> str:
        raw = f"{type}:{str(value).lower().strip()}"
        return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]

    def _save(self, node: Dict):
        filename = f"{node['id']}_{int(time.time())}.json"
        file_path = self.results_root / filename
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(node, f, indent=2, ensure_ascii=False)
        if self.es:
            try: self.es.index(index=self.es_index, id=node['id'], body=node)
            except: pass
