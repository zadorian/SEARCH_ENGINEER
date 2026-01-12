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
# 6 = domain_url, 193 = domain_dns_records, 195 = domain_whois_history

# --- Handler ---
class DomainUrlOutputHandler:
    def __init__(self):
        self.results_root = Path(__file__).resolve().parent.parent / 'results' / 'domain_url'
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
        node_id = self._generate_id('domain', value)
        edges = []
        
        # --- Structured Data ---
        structured_data = {}
        if raw_data:
            # WHOIS History - Legend 195: domain_whois_history
            records = raw_data.get('records', [])
            if not records and 'registryData' in raw_data:
                records = [raw_data]
                
            if records:
                history_entries = []
                for rec in records:
                    reg = rec.get('registrant', {}) or rec.get('registrantContact', {})
                    entry = {
                        "_code": 195,
                        "observed_at": rec.get('audit', {}).get('updatedDate') or rec.get('updatedDate') or datetime.utcnow().isoformat(),
                        "registrar": rec.get('registrarName'),
                        "registrant": reg.get('organization') or reg.get('name'),
                        "registrant_email": rec.get('contactEmail'),
                        "name_servers": rec.get('nameServers', {}).get('hostNames', []),
                        "raw": rec
                    }
                    history_entries.append(entry)
                structured_data['whois_history'] = history_entries

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

        comment_payload = None
        if structured_data:
            comment_payload = json.dumps(structured_data, indent=2, ensure_ascii=False)
        elif raw_data:
            comment_payload = json.dumps(raw_data, indent=2, ensure_ascii=False)

        node = {
            "id": node_id,
            "node_class": "ENTITY",
            "type": "domain",
            "_code": 6,  # Legend 6: domain_url
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
