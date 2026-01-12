import datetime
from typing import Dict, Any
from .url import UrlOutputHandler

class TwitterUrlOutputHandler(UrlOutputHandler):
    def __init__(self):
        super().__init__(platform="twitter")

    def process(self, value: str, context: Dict[str, Any], raw_data: Dict[str, Any] = None) -> Dict[str, Any]:
        node = super().process(value, context, raw_data)
        
        # Link to Twitter Platform
        platform_id = self._generate_id('platform', 'twitter')
        
        exists = any(e['target_id'] == platform_id for e in node['embedded_edges'])
        if not exists:
            node['embedded_edges'].append({
                "target_id": platform_id,
                "relation": "account_on",
                "verification_status": "VERIFIED",
                "connection_reason": "platform_url"
            })
            
        self._create_platform_node('twitter', platform_id)
        self._save(node)
        return node

    def _create_platform_node(self, name: str, node_id: str):
        if self.es:
            node = {
                "id": node_id,
                "node_class": "LOCATION",
                "type": "platform",
                "canonicalValue": name,
                "label": name.title(),
                "value": name,
                "embedded_edges": [],
                "metadata": {"type": "social_platform"},
                "createdAt": datetime.datetime.utcnow().isoformat(),
                "updatedAt": datetime.datetime.utcnow().isoformat(),
                "lastSeen": datetime.datetime.utcnow().isoformat()
            }
            try: self.es.index(index=self.es_index, id=node_id, body=node)
            except: pass