"""
ALLDOM Domain URL Output Handler

Creates C1 graph nodes for domain entities with proper Legend code integration.
Uses codes.json schema for structured data instead of JSON comment stuffing.

Legend Codes Used:
- 6: domain_url (entity node)
- 193: domain_dns_records (dataset node)
- 195: domain_whois_history (dataset node)
- 200: domain_subdomains (dataset node)
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


class DomainUrlOutputHandler:
    """
    Handles domain entity output with Legend-compliant schema.

    Creates:
    - Domain entity node (_code: 6)
    - WHOIS history nodes (_code: 195) with registered_by edges
    - DNS record nodes (_code: 193) as metadata
    - Subdomain nodes (_code: 200) with subdomain_of edges
    """

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
        """
        Process domain entity and create graph nodes.

        Returns the primary domain node with embedded edges to related nodes.
        Also creates secondary nodes (whois records, dns records) as needed.
        """
        node_id = self._generate_id('domain', value)
        edges = []
        secondary_nodes = []

        if raw_data:
            # --- Legend 195: WHOIS History ---
            whois_nodes = self._create_whois_nodes(value, raw_data)
            for whois_node in whois_nodes:
                secondary_nodes.append(whois_node)
                edges.append({
                    "target_id": whois_node['id'],
                    "relation": "registered_by",  # Legend 195 edge_type
                    "_code": 195,
                    "verification_status": "VERIFIED",
                    "connection_reason": "whois_lookup"
                })

                # Direct entity links from WHOIS
                if whois_node.get('registrant_email'):
                    email_id = self._generate_id('email', whois_node['registrant_email'])
                    edges.append({
                        "target_id": email_id,
                        "relation": "contact_email",
                        "_code": 195,
                        "verification_status": "VERIFIED",
                        "connection_reason": "whois_record"
                    })

                if whois_node.get('registrant'):
                    person_id = self._generate_id('person', whois_node['registrant'])
                    edges.append({
                        "target_id": person_id,
                        "relation": "owned_by",
                        "_code": 195,
                        "verification_status": "VERIFIED",
                        "connection_reason": "whois_record"
                    })

            # --- Legend 193: DNS Records ---
            if raw_data.get('dns_records'):
                dns_node = self._create_dns_node(value, raw_data['dns_records'])
                secondary_nodes.append(dns_node)
                edges.append({
                    "target_id": dns_node['id'],
                    "relation": "has_dns",
                    "_code": 193,
                    "verification_status": "VERIFIED",
                    "connection_reason": "dns_lookup"
                })

            # --- Legend 200: Subdomains ---
            if raw_data.get('subdomains'):
                for subdomain in raw_data['subdomains']:
                    sub_node = self._create_subdomain_node(value, subdomain)
                    secondary_nodes.append(sub_node)
                    edges.append({
                        "target_id": sub_node['id'],
                        "relation": "subdomain_of",  # Legend 200 edge_type
                        "_code": 200,
                        "verification_status": "VERIFIED",
                        "connection_reason": "subdomain_discovery"
                    })

        # Provenance edges
        provenance_edges = self._create_provenance_edges(context)
        edges.extend(provenance_edges)

        # --- Primary Domain Node (Legend 6) ---
        node = {
            "id": node_id,
            "node_class": "ENTITY",
            "type": "domain",
            "_code": 6,
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

    def _create_whois_nodes(self, domain: str, raw_data: Dict) -> List[Dict]:
        """
        Create WHOIS history nodes (Legend 195).

        Fields per codes.json: registrant, registrar, created_date, updated_date, expiry_date, nameservers
        """
        nodes = []
        records = raw_data.get('records', [])
        if not records and 'registryData' in raw_data:
            records = [raw_data]

        for i, rec in enumerate(records):
            reg = rec.get('registrant', {}) or rec.get('registrantContact', {})
            observed_at = rec.get('audit', {}).get('updatedDate') or rec.get('updatedDate') or datetime.utcnow().isoformat()

            whois_id = self._generate_id('whois', f"{domain}:{observed_at}:{i}")

            node = {
                "id": whois_id,
                "node_class": "DATASET",
                "type": "whois_record",
                "_code": 195,
                "canonicalValue": f"{domain}:{observed_at}",
                "label": f"WHOIS: {domain}",
                # Legend 195 fields
                "registrant": reg.get('organization') or reg.get('name'),
                "registrant_email": rec.get('contactEmail'),
                "registrar": rec.get('registrarName'),
                "created_date": rec.get('createdDate'),
                "updated_date": rec.get('updatedDate'),
                "expiry_date": rec.get('expiresDate'),
                "nameservers": rec.get('nameServers', {}).get('hostNames', []),
                # Metadata
                "embedded_edges": [],
                "metadata": {
                    "observed_at": observed_at,
                    "raw_data": rec
                },
                "createdAt": datetime.utcnow().isoformat()
            }
            nodes.append(node)

        return nodes

    def _create_dns_node(self, domain: str, dns_records: List[Dict]) -> Dict:
        """
        Create DNS records node (Legend 193).

        Fields per codes.json: record_type, value, ttl, observed_at
        """
        dns_id = self._generate_id('dns', f"{domain}:{datetime.utcnow().isoformat()}")

        return {
            "id": dns_id,
            "node_class": "DATASET",
            "type": "dns_records",
            "_code": 193,
            "canonicalValue": domain,
            "label": f"DNS: {domain}",
            # Legend 193 fields stored as array
            "records": [
                {
                    "record_type": r.get('type'),
                    "value": r.get('value'),
                    "ttl": r.get('ttl'),
                    "observed_at": r.get('observed_at', datetime.utcnow().isoformat())
                }
                for r in dns_records
            ],
            "embedded_edges": [],
            "metadata": {"raw_data": dns_records},
            "createdAt": datetime.utcnow().isoformat()
        }

    def _create_subdomain_node(self, parent_domain: str, subdomain_data: Dict) -> Dict:
        """
        Create subdomain node (Legend 200).

        Fields per codes.json: subdomain, ip, discovered_at, source
        """
        subdomain = subdomain_data if isinstance(subdomain_data, str) else subdomain_data.get('subdomain', '')
        sub_id = self._generate_id('domain', subdomain)

        return {
            "id": sub_id,
            "node_class": "ENTITY",
            "type": "domain",
            "_code": 200,
            "canonicalValue": subdomain.lower(),
            "label": subdomain,
            "value": subdomain,
            # Legend 200 fields
            "subdomain": subdomain,
            "parent_domain": parent_domain,
            "ip": subdomain_data.get('ip') if isinstance(subdomain_data, dict) else None,
            "discovered_at": subdomain_data.get('discovered_at', datetime.utcnow().isoformat()) if isinstance(subdomain_data, dict) else datetime.utcnow().isoformat(),
            "source": subdomain_data.get('source') if isinstance(subdomain_data, dict) else None,
            "embedded_edges": [],
            "metadata": {},
            "createdAt": datetime.utcnow().isoformat()
        }

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
