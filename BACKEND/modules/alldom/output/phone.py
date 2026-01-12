import json
import os
import hashlib
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

try:
    from elasticsearch import Elasticsearch
    ES_AVAILABLE = True
except ImportError:
    ES_AVAILABLE = False

# Legend codes from /data/SEARCH_ENGINEER/BACKEND/modules/input_output/matrix/codes.json
# 2 = phone

class PhoneOutputHandler:
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
        node_id = self._generate_id('phone', value)
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

        # Link to source domain if provided
        if context.get('source_domain'):
            domain_id = self._generate_id('domain', context['source_domain'])
            edges.append({
                "target_id": domain_id,
                "relation": "registrant_of",
                "verification_status": "VERIFIED",
                "connection_reason": "whois_record"
            })

        node = {
            "id": node_id,
            "node_class": "ENTITY",
            "type": "phone",
            "_code": 2,
            "canonicalValue": value.strip(),
            "label": value,
            "value": value,
            "comment": json.dumps(raw_data, indent=2, ensure_ascii=False) if raw_data else None,
            "embedded_edges": edges,
            "metadata": context.get('metadata', {}),
            "createdAt": datetime.utcnow().isoformat(),
            "updatedAt": datetime.utcnow().isoformat(),
            "lastSeen": datetime.utcnow().isoformat()
        }
        
        self._save(node)
        return node

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
