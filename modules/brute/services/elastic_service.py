#!/usr/bin/env python3
"""
Elasticsearch Service - Lightweight Async Client for Search Engineer
Handles real-time indexing of search results and nodes for the Grid/Graph frontend.
"""

import aiohttp
import logging
import json
import os
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

class ElasticService:
    """
    Lightweight Async Elasticsearch Client.
    Indexes search results as 'nodes' to power the Grid/Graph.

    CYMONIDES MANDATE: project_id is REQUIRED. Index pattern: cymonides-1-{project_id}.
    Edges are EMBEDDED in nodes (no separate edge index).
    """

    def __init__(self, hosts: List[str] = None, index_name: str = None, project_id: str = None):
        """
        Initialize ElasticService.

        CYMONIDES MANDATE: Either index_name or project_id must be provided.
        If project_id is provided, index_name = cymonides-1-{project_id}.
        """
        self.hosts = hosts or [os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")]
        self.project_id = project_id

        # CYMONIDES MANDATE: Derive index from project_id
        if index_name:
            self.index_name = index_name
        elif project_id:
            self.index_name = f"cymonides-1-{project_id}"
        else:
            # Allow None for lazy initialization - will require set_project_id() before use
            self.index_name = None

        self.session = None
        self._initialized = False

    def set_project_id(self, project_id: str):
        """Set project_id and derive index name. Required if not set in __init__."""
        self.project_id = project_id
        self.index_name = f"cymonides-1-{project_id}"
        self._initialized = False  # Force re-initialization with new index

    async def _get_session(self):
        if not self.session:
            self.session = aiohttp.ClientSession(
                headers={"Content-Type": "application/json"}
            )
        return self.session

    async def initialize(self):
        """Ensure index exists with proper mapping"""
        if self._initialized:
            return

        # CYMONIDES MANDATE: Require index_name before initialization
        if not self.index_name:
            raise ValueError("CYMONIDES MANDATE: project_id or index_name required. Call set_project_id() first.")

        session = await self._get_session()

        async def ensure_mapping_fields(index_name: str, index_url: str, expected_properties: Dict[str, Any], label: str):
            """Ensure required fields exist on an already-created index."""
            try:
                async with session.get(f"{index_url}/_mapping") as mapping_resp:
                    if mapping_resp.status != 200:
                        return
                    mapping_json = await mapping_resp.json()
                    props = mapping_json.get(index_name, {}).get("mappings", {}).get("properties", {})

                    # Handle cases where the index name is an alias or nested differently
                    if not props and isinstance(mapping_json, dict) and len(mapping_json) == 1:
                        props = next(iter(mapping_json.values())).get("mappings", {}).get("properties", {})

                    missing_fields = {k: v for k, v in expected_properties.items() if k not in props}
                    if not missing_fields:
                        return

                    async with session.put(f"{index_url}/_mapping", json={"properties": missing_fields}) as put_resp:
                        if put_resp.status not in (200, 201):
                            text = await put_resp.text()
                            logger.error(f"Failed to update mapping for {label}: {text}")
                        else:
                            logger.info(f"Updated mapping for {label}; added {', '.join(missing_fields.keys())}")
            except Exception as e:
                logger.error(f"Error updating mapping for {label}: {e}")

        # Create index with mapping if it doesn't exist
        mapping = {
            "mappings": {
                "properties": {
                    # Core Identity
                    "id": {"type": "keyword"},
                    "canonicalValue": {"type": "keyword"},
                    "label": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                    "node_class": {"type": "keyword"},
                    "type": {"type": "keyword"},
                    "className": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                    "typeName": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                    "class": {"type": "keyword"},

                    # Hierarchy
                    "section": {"type": "keyword"},
                    "section_subtype": {"type": "keyword"},
                    "jurisdiction": {"type": "keyword"},
                    "suite": {"type": "keyword"},
                    "friction": {"type": "keyword"},

                    # About (Structured)
                    "about": {
                        "properties": {
                            "company_number": {"type": "keyword"},
                            "identifier": {
                                "properties": {
                                    "registration_number": {"type": "keyword"},
                                    "tax_number": {"type": "keyword"},
                                    "lei": {"type": "keyword"}
                                }
                            },
                            "jurisdiction": {"type": "keyword"},
                            "registered_address": {
                                "properties": {
                                    "value": {"type": "text", "fields": {"keyword": {"type": "keyword"}}}
                                }
                            },
                            "website": {"properties": {"value": {"type": "keyword"}}},
                            "contact_details": {
                                "properties": {
                                    "phone": {"properties": {"value": {"type": "keyword"}}},
                                    "email": {"properties": {"value": {"type": "keyword"}}}
                                }
                            }
                        }
                    },

                    # Exploded
                    "vat_numbers": {"type": "keyword"},
                    "lei_codes": {"type": "keyword"},
                    "duns_numbers": {"type": "keyword"},
                    "email_addresses": {"type": "keyword"},
                    "email_domains": {"type": "keyword"},
                    "phone_numbers": {"type": "keyword"},
                    "ip_addresses": {"type": "keyword"},
                    "ga_codes": {"type": "keyword"},
                    "gtm_codes": {"type": "keyword"},
                    "nameserver_pairs": {"type": "keyword"},
                    "ssl_cert_serials": {"type": "keyword"},
                    "imo_numbers": {"type": "keyword"},
                    "mmsi_numbers": {"type": "keyword"},
                    "aircraft_tail": {"type": "keyword"},
                    "vin_numbers": {"type": "keyword"},
                    "iban_numbers": {"type": "keyword"},
                    "swift_codes": {"type": "keyword"},
                    "crypto_addresses": {"type": "keyword"},
                    "domains": {"type": "keyword"},
                    "urls": {"type": "keyword"},
                    "social_handles": {"type": "keyword"},

                    # Person
                    "person_nationality": {"type": "keyword"},
                    "person_gender": {"type": "keyword"},
                    "person_title": {"type": "keyword"},

                    # Assets
                    "assets": {
                        "properties": {
                            "property": {"properties": {"value": {"type": "keyword"}}},
                            "vehicle": {"properties": {"value": {"type": "keyword"}}},
                            "other": {"properties": {"value": {"type": "keyword"}}}
                        }
                    },
                    "asset_value": {"type": "float"},
                    "asset_currency": {"type": "keyword"},

                    # System
                    "status": {"type": "keyword"},
                    "userId": {"type": "integer"},
                    "projectId": {"type": "keyword"},
                    "ordering": {"type": "integer"},
                    "weight": {"type": "float"},
                    "metadata": {
                        "type": "object",
                        "enabled": True,
                        "properties": {
                            "codes": {"type": "integer"},
                            "suite": {"type": "keyword"},
                            "raw_properties": {"type": "object", "enabled": False}
                        }
                    },
                    "timestamp": {"type": "date"},
                    "createdAt": {"type": "date"},
                    "lastSeen": {"type": "date"},
                    "updatedAt": {"type": "date"},
                    "query": {"type": "text"},
                    "content": {"type": "text"}
                }
            }
        }

        # Initialize Nodes Index
        url = f"{self.hosts[0]}/{self.index_name}"
        try:
            async with session.head(url) as resp:
                if resp.status == 404:
                    async with session.put(url, json=mapping) as create_resp:
                        if create_resp.status in (200, 201):
                            logger.info(f"Created index: {self.index_name}")
                        else:
                            text = await create_resp.text()
                            logger.error(f"Failed to create index: {text}")
                else:
                    await ensure_mapping_fields(self.index_name, url, mapping["mappings"]["properties"], self.index_name)
        except Exception as e:
            logger.error(f"Error initializing index: {e}")

        # CYMONIDES MANDATE: No separate edges index - edges are EMBEDDED in nodes
        # The embedded_edges field is already part of the node mapping (nested type)

        self._initialized = True

    async def delete_document(self, doc_id: str, index_type: str = None):
        """Delete a document by ID"""
        await self.initialize()
        # CYMONIDES MANDATE: No separate edges index - edges are EMBEDDED in nodes
        if index_type == "edges":
            logger.warning("CYMONIDES MANDATE: Separate edge operations deprecated. Edges are embedded in nodes.")
            return False
        target_index = self.index_name
        url = f"{self.hosts[0]}/{target_index}/_doc/{doc_id}"
        
        try:
            session = await self._get_session()
            async with session.delete(url) as resp:
                if resp.status == 404:
                    return False
                if resp.status not in (200, 204):
                    text = await resp.text()
                    logger.error(f"Failed to delete document {doc_id}: {text}")
                    return False
                return True
        except Exception as e:
            logger.error(f"Error deleting document: {e}")
            return False

    async def index_document(self, doc: Dict[str, Any], index_type: str = None):
        """Index a single document (convenience wrapper)."""
        await self.index_batch([doc], index_type=index_type)

    async def index_batch(self, docs: List[Dict[str, Any]], index_type: str = None):
        """Index a batch of documents using _bulk API"""
        await self.initialize()

        if not docs:
            return

        # CYMONIDES MANDATE: No separate edges index - edges are EMBEDDED in nodes
        if index_type == "edges":
            logger.warning("CYMONIDES MANDATE: Separate edge indexing deprecated. Embed edges in source nodes.")
            return False

        session = await self._get_session()
        target_index = self.index_name

        # Build bulk request body
        bulk_body = []
        for doc in docs:
            doc_id = doc.get('id', f"doc_{datetime.utcnow().timestamp()}")

            # Action line
            bulk_body.append(json.dumps({"index": {"_index": target_index, "_id": doc_id}}))
            # Document line
            bulk_body.append(json.dumps(doc))

        # Join with newlines and add trailing newline
        bulk_data = '\n'.join(bulk_body) + '\n'

        url = f"{self.hosts[0]}/_bulk?refresh=wait_for"

        try:
            async with session.post(
                url,
                data=bulk_data,
                headers={"Content-Type": "application/x-ndjson"}
            ) as resp:
                if resp.status not in (200, 201):
                    text = await resp.text()
                    logger.error(f"Bulk indexing failed: {text}")
                    return False

                result = await resp.json()
                if result.get('errors'):
                    logger.warning(f"Some documents failed to index")
                    # Log first few errors
                    for item in result.get('items', [])[:5]:
                        if 'error' in item.get('index', {}):
                            logger.error(f"Index error: {item['index']['error']}")

                return True
        except Exception as e:
            logger.error(f"Error during bulk indexing: {e}")
            return False

    async def search(self, query_body: Dict, index_type: str = None) -> Dict:
        """Execute a raw search query"""
        await self.initialize()
        # CYMONIDES MANDATE: No separate edges index - use nested query on embedded_edges
        if index_type == "edges":
            logger.warning("CYMONIDES MANDATE: Separate edge search deprecated. Use nested query on embedded_edges.")
            return {"hits": {"hits": []}}
        target_index = self.index_name
        url = f"{self.hosts[0]}/{target_index}/_search"
        try:
            session = await self._get_session()
            async with session.post(url, json=query_body) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    logger.error(f"Search failed: {text}")
                    return {"hits": {"hits": []}}
                return await resp.json()
        except Exception as e:
            logger.error(f"Search error: {e}")
            return {"hits": {"hits": []}}

    async def aggregate_field(self, field: str, query: str = None, size: int = 50) -> Dict[str, int]:
        """Perform a terms aggregation"""
        await self.initialize()
        target_index = self.index_name
        
        # Ensure field is keyword for agg
        agg_field = f"{field}.keyword" if not field.endswith(".keyword") and field not in ["id", "className", "typeName", "projectId"] else field
        
        es_query = {
            "size": 0,
            "aggs": {
                "terms_agg": {
                    "terms": {"field": agg_field, "size": size}
                }
            }
        }
        
        if query:
            es_query["query"] = {
                "multi_match": {
                    "query": query,
                    "fields": ["label", "content"]
                }
            }
            
        url = f"{self.hosts[0]}/{target_index}/_search"
        try:
            session = await self._get_session()
            async with session.post(url, json=es_query) as resp:
                if resp.status != 200: return {}
                data = await resp.json()
                buckets = data.get("aggregations", {}).get("terms_agg", {}).get("buckets", [])
                return {b["key"]: b["doc_count"] for b in buckets}
        except Exception as e:
            logger.error(f"Agg error: {e}")
            return {}

    async def close(self):
        if self.session:
            await self.session.close()

# Singleton instance
_elastic_service = None

def get_elastic_service():
    global _elastic_service
    if _elastic_service is None:
        _elastic_service = ElasticService()
    return _elastic_service
