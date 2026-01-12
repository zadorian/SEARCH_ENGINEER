#!/usr/bin/env python3
"""
LINKLATER -> Cymonides-1 Bridge

Indexes CLINK discovery results to cymonides-1-{projectId} with:
- Entity nodes (person, company, email, domain)
- Source nodes (web pages/URLs)
- Embedded edges (found_on, mentions, co_occurs_with)

Index Structure:
  cymonides-1-{projectId}  (per-project graph)
  cymonides-1-linklater    (default for LINKLATER discoveries)

Node Types:
  - entity: person, company, email, phone, domain
  - source: webpage, domain

Edge Types (per relationships.json):
  - found_on: entity -> source (entity was found on this page)
  - mentions: source -> entity (page mentions entity)
  - co_occurs_with: entity -> entity (entities found on same page)

Usage:
    from c1_bridge import C1Bridge
    
    bridge = C1Bridge(project_id="my-project")
    
    # Index CLINK results
    clink_results = await nexus_bridge.discover_related(entities)
    stats = bridge.index_clink_results(clink_results, source_domain="example.com")
"""

import hashlib
import json
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field, asdict

from elasticsearch import Elasticsearch, helpers

logger = logging.getLogger(__name__)

# Default index for LINKLATER discoveries
DEFAULT_INDEX = "cymonides-1-linklater"


@dataclass
class EmbeddedEdge:
    """Edge embedded within a node document."""
    target_id: str
    target_class: str  # source, entity
    target_type: str   # person, company, webpage, etc.
    target_label: str
    relation: str      # found_on, mentions, co_occurs_with
    direction: str = "outgoing"
    confidence: float = 0.85
    metadata: Dict = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class C1Node:
    """Node for cymonides-1-{projectId} index."""
    id: str
    node_class: str = "entity"  # entity, source
    type: str = "company"       # person, company, email, domain, webpage
    label: str = ""
    canonicalValue: str = ""
    
    # Metadata
    metadata: Dict = field(default_factory=dict)
    
    # Source tracking
    sources: List[str] = field(default_factory=list)
    source_system: str = "linklater"
    
    # Embedded edges
    embedded_edges: List[Dict] = field(default_factory=list)
    
    # Timestamps
    createdAt: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updatedAt: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    lastSeen: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    
    # Project
    projectId: Optional[str] = None
    
    def to_dict(self) -> Dict:
        d = asdict(self)
        d['className'] = d['node_class']
        d['typeName'] = d['type']
        d['class'] = d['node_class']
        return d


class C1Bridge:
    """
    Bridge from LINKLATER to Cymonides-1 graph storage.
    
    Handles:
    - Node creation with deterministic IDs
    - Edge embedding (no separate edge index)
    - Project-scoped indices
    - Deduplication
    """
    
    # Entity type normalization
    TYPE_MAP = {
        'person': 'person',
        'company': 'company',
        'organization': 'company',
        'email': 'email',
        'phone': 'phone',
        'domain': 'domain',
        'whois': 'domain',
        'url': 'webpage',
        'webpage': 'webpage',
        'username': 'username',
        'ip': 'ip',
        'ip_address': 'ip',
        'password': 'password',
        'hash': 'password',
        'hashed_password': 'password',
        'linkedin': 'linkedin',
        'linkedin_url': 'linkedin',
        'unknown': 'entity',
    }
    
    # Index mapping
    MAPPING = {
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 0
        },
        "mappings": {
            "properties": {
                "id": {"type": "keyword"},
                "node_class": {"type": "keyword"},
                "type": {"type": "keyword"},
                "label": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                "canonicalValue": {"type": "keyword"},
                "sources": {"type": "keyword"},
                "source_system": {"type": "keyword"},
                "projectId": {"type": "keyword"},
                "createdAt": {"type": "date"},
                "updatedAt": {"type": "date"},
                "lastSeen": {"type": "date"},
                "metadata": {"type": "object", "enabled": False},
                "embedded_edges": {
                    "type": "nested",
                    "properties": {
                        "target_id": {"type": "keyword"},
                        "target_class": {"type": "keyword"},
                        "target_type": {"type": "keyword"},
                        "target_label": {"type": "text"},
                        "relation": {"type": "keyword"},
                        "direction": {"type": "keyword"},
                        "confidence": {"type": "float"},
                        "created_at": {"type": "date"}
                    }
                }
            }
        }
    }
    
    def __init__(self, project_id: str = None, es_host: str = "http://localhost:9200"):
        self.project_id = project_id
        self.es = Elasticsearch([es_host])
        self._ensure_index()
    
    def _get_index_name(self) -> str:
        if self.project_id:
            return f"cymonides-1-{self.project_id}"
        return DEFAULT_INDEX
    
    def _ensure_index(self) -> None:
        index_name = self._get_index_name()
        if not self.es.indices.exists(index=index_name):
            logger.info(f"Creating index: {index_name}")
            self.es.indices.create(index=index_name, body=self.MAPPING)
    
    def _generate_id(self, value: str, node_type: str) -> str:
        """Generate deterministic node ID."""
        key = f"{node_type}:{value.lower().strip()}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]
    
    def _normalize_type(self, entity_type: str) -> str:
        return self.TYPE_MAP.get(entity_type.lower(), 'entity')
    
    def create_entity_node(
        self,
        value: str,
        entity_type: str,
        source_url: str = None,
        confidence: float = 0.85
    ) -> C1Node:
        """Create an entity node."""
        node_type = self._normalize_type(entity_type)
        node_id = self._generate_id(value, node_type)
        
        node = C1Node(
            id=node_id,
            node_class="entity",
            type=node_type,
            label=value,
            canonicalValue=value.lower().strip(),
            sources=[source_url] if source_url else [],
            source_system="linklater",
            projectId=self.project_id,
            metadata={"original_type": entity_type, "confidence": confidence}
        )
        
        return node
    
    def create_source_node(
        self,
        url: str,
        title: str = "",
        domain: str = ""
    ) -> C1Node:
        """Create a source (webpage) node."""
        node_id = self._generate_id(url, "webpage")
        
        node = C1Node(
            id=node_id,
            node_class="source",
            type="webpage",
            label=title or url,
            canonicalValue=url.lower().strip(),
            sources=[url],
            source_system="linklater",
            projectId=self.project_id,
            metadata={"domain": domain, "url": url, "title": title}
        )
        
        return node
    
    def add_edge(
        self,
        node: C1Node,
        target_node: C1Node,
        relation: str,
        confidence: float = 0.85
    ) -> None:
        """Add an embedded edge to a node."""
        edge = EmbeddedEdge(
            target_id=target_node.id,
            target_class=target_node.node_class,
            target_type=target_node.type,
            target_label=target_node.label,
            relation=relation,
            direction="outgoing",
            confidence=confidence
        )
        edge_dict = asdict(edge)
        # Deduplicate by (target_id, relation, direction) within this run
        for existing in node.embedded_edges:
            if (
                existing.get("target_id") == edge_dict["target_id"]
                and existing.get("relation") == edge_dict["relation"]
                and existing.get("direction") == edge_dict["direction"]
            ):
                return
        node.embedded_edges.append(edge_dict)

    def _bulk_upsert_nodes(
        self,
        nodes: List[C1Node],
        index_name: str,
    ) -> tuple[int, list]:
        """
        Upsert nodes to Elasticsearch without clobbering embedded_edges/sources.

        C-1 edges are embedded in node documents; overwriting loses graph history.
        """
        now = datetime.utcnow().isoformat()

        upsert_script = {
            "source": """
                // Merge sources
                if (ctx._source.sources == null) { ctx._source.sources = []; }
                for (s in params.sources) {
                    if (s != null && s.length() > 0 && !ctx._source.sources.contains(s)) {
                        ctx._source.sources.add(s);
                    }
                }

                // Merge embedded_edges (dedupe by target_id+relation+direction)
                if (ctx._source.embedded_edges == null) { ctx._source.embedded_edges = []; }
                for (e in params.edges) {
                    if (e == null) { continue; }
                    boolean exists = false;
                    for (existing in ctx._source.embedded_edges) {
                        if (
                            existing.target_id == e.target_id
                            && existing.relation == e.relation
                            && existing.direction == e.direction
                        ) {
                            exists = true;
                            break;
                        }
                    }
                    if (!exists) {
                        ctx._source.embedded_edges.add(e);
                    }
                }

                // Merge metadata
                if (ctx._source.metadata == null) { ctx._source.metadata = params.metadata; }
                else if (params.metadata != null) { ctx._source.metadata.putAll(params.metadata); }

                // Fill missing identity fields only (avoid surprises)
                if (ctx._source.label == null || ctx._source.label.length() == 0) { ctx._source.label = params.label; }
                if (ctx._source.canonicalValue == null || ctx._source.canonicalValue.length() == 0) { ctx._source.canonicalValue = params.canonicalValue; }
                if (ctx._source.source_system == null || ctx._source.source_system.length() == 0) { ctx._source.source_system = params.source_system; }
                if (ctx._source.projectId == null || ctx._source.projectId.length() == 0) { ctx._source.projectId = params.projectId; }

                // Touch timestamps
                ctx._source.updatedAt = params.now;
                ctx._source.lastSeen = params.now;
            """,
            "lang": "painless",
        }

        def generate_docs():
            for node in nodes:
                node_doc = node.to_dict()
                yield {
                    "_op_type": "update",
                    "_index": index_name,
                    "_id": node.id,
                    "retry_on_conflict": 3,
                    "script": {
                        **upsert_script,
                        "params": {
                            "sources": node_doc.get("sources", []),
                            "edges": node_doc.get("embedded_edges", []),
                            "metadata": node_doc.get("metadata", {}),
                            "label": node_doc.get("label", ""),
                            "canonicalValue": node_doc.get("canonicalValue", ""),
                            "source_system": node_doc.get("source_system", ""),
                            "projectId": node_doc.get("projectId"),
                            "now": now,
                        },
                    },
                    "upsert": node_doc,
                }

        return helpers.bulk(self.es, generate_docs(), raise_on_error=False)
    
    def index_clink_results(
        self,
        clink_results: Dict[str, Any],
        source_domain: str = None
    ) -> Dict[str, Any]:
        """
        Index CLINK discovery results to Cymonides-1.
        
        Creates:
        - Entity nodes for each searched entity
        - Source nodes for each related site found
        - Edges: entity -[found_on]-> source
        - Edges: entity -[co_occurs_with]-> entity (if on same page)
        
        Args:
            clink_results: Results from CLINK.discover()
            source_domain: Original domain (excluded from sources)
            
        Returns:
            Stats dict with counts
        """
        nodes_created = {}  # id -> node
        
        # 1. Create entity nodes from the searched entities
        combo_results = clink_results.get("combo_results", {})
        entity_nodes = {}
        
        # Extract unique entities from combo keys
        for combo_key in combo_results.keys():
            entities = combo_key.split(" + ")
            for entity_value in entities:
                if entity_value not in entity_nodes:
                    # Infer type (basic heuristic)
                    if "@" in entity_value:
                        entity_type = "email"
                    elif "." in entity_value and " " not in entity_value:
                        entity_type = "domain"
                    elif any(c.isdigit() for c in entity_value) and len(entity_value) < 20:
                        entity_type = "phone"
                    else:
                        # Default to company unless has common name patterns
                        entity_type = "company"
                    
                    node = self.create_entity_node(entity_value, entity_type)
                    entity_nodes[entity_value] = node
                    nodes_created[node.id] = node
        
        # 2. Create source nodes for related sites
        source_nodes = {}
        for site in clink_results.get("related_sites", []):
            url = site.get("url", "")
            domain = site.get("domain", "")
            
            # Skip source domain
            if source_domain and domain == source_domain:
                continue
            
            if url not in source_nodes:
                node = self.create_source_node(
                    url=url,
                    title=site.get("title", ""),
                    domain=domain
                )
                source_nodes[url] = node
                nodes_created[node.id] = node
            
            # 3. Create edges from entities to this source
            matched_entities = site.get("matched_entities", [])
            for entity_value in matched_entities:
                if entity_value in entity_nodes:
                    entity_node = entity_nodes[entity_value]
                    source_node = source_nodes[url]
                    
                    # Entity found on source
                    self.add_edge(
                        entity_node,
                        source_node,
                        relation="found_on",
                        confidence=0.9
                    )
                    
                    # Source mentions entity
                    self.add_edge(
                        source_node,
                        entity_node,
                        relation="mentions",
                        confidence=0.9
                    )
            
            # 4. Create co_occurs_with edges between entities on same page
            if len(matched_entities) > 1:
                for i, e1 in enumerate(matched_entities):
                    for e2 in matched_entities[i+1:]:
                        if e1 in entity_nodes and e2 in entity_nodes:
                            self.add_edge(
                                entity_nodes[e1],
                                entity_nodes[e2],
                                relation="co_occurs_with",
                                confidence=0.85
                            )
                            self.add_edge(
                                entity_nodes[e2],
                                entity_nodes[e1],
                                relation="co_occurs_with",
                                confidence=0.85
                            )
        
        # 5. Bulk upsert to Elasticsearch (avoid clobbering embedded edges)
        index_name = self._get_index_name()

        success, errors = self._bulk_upsert_nodes(list(nodes_created.values()), index_name)
        
        if errors:
            logger.warning(f"Indexing errors: {len(errors)}")
        
        self.es.indices.refresh(index=index_name)
        
        stats = {
            "index": index_name,
            "entities_indexed": len(entity_nodes),
            "sources_indexed": len(source_nodes),
            "total_nodes": success,
            "errors": len(errors) if errors else 0
        }
        
        logger.info(f"Indexed {stats['total_nodes']} nodes to {index_name}")
        return stats
    
    def index_eyed_results(
        self,
        eyed_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Index EYE-D OSINT results to Cymonides-1.
        
        Maps EYE-D structure to Graph:
        - Query -> Main Entity Node
        - Result Entry -> Source Node (eyed://source/value)
        - Extracted Entities -> Entity Nodes
        - Edges: Main-[found_on]->Source, Extracted-[co_occurs_with]->Main
        
        Args:
            eyed_results: Dict from EyeDSearchHandler.search_*
            
        Returns:
            Stats dict
        """
        nodes_to_index = {}  # id -> node
        
        # 1. Create Main Entity Node (The Query)
        query_value = eyed_results.get('query', '')
        query_type = eyed_results.get('subtype', 'unknown')
        
        if not query_value:
            return {"error": "No query value"}
            
        main_node = self.create_entity_node(query_value, query_type, confidence=1.0)
        main_node.source_system = "eyed"
        nodes_to_index[main_node.id] = main_node
        
        # 2. Process Results (Sources)
        # Group by source to avoid creating too many duplicate source nodes
        for result in eyed_results.get('results', []):
            source_name = result.get('source', 'eyed_unknown')
            
            # Create Source Node
            # Use specific record URL if available, else generic provider URL
            data = result.get('data', {})
            source_url = data.get('url') if isinstance(data, dict) else None
            
            if not source_url:
                # Construct deterministic pseudo-URL for this search result
                source_url = f"eyed://{source_name}/{query_type}/{query_value}"

            source_id = self._generate_id(source_url, "webpage")
            if source_id not in nodes_to_index:
                source_node = self.create_source_node(
                    url=source_url,
                    title=f"EYE-D Search: {source_name}",
                    domain=source_name,
                )
                source_node.source_system = "eyed"
                nodes_to_index[source_node.id] = source_node
            else:
                source_node = nodes_to_index[source_id]

            # Link Main Entity <-> Source
            self.add_edge(main_node, source_node, "found_on", 0.95)
            self.add_edge(source_node, main_node, "mentions", 0.95)
            
        # 3. Process Extracted Entities (prefer deterministic extraction if present)
        entities = eyed_results.get('extracted_entities') or eyed_results.get('entities', [])
        for entity in entities:
            e_type = entity.get('type', 'unknown')
            e_value = entity.get('value')
            
            if not e_value:
                continue
                
            # Create Entity Node
            entity_node = self.create_entity_node(e_value, e_type, confidence=0.9)
            entity_node.source_system = "eyed"
            
            if entity_node.id not in nodes_to_index:
                nodes_to_index[entity_node.id] = entity_node
            else:
                entity_node = nodes_to_index[entity_node.id]
            
            # Link to Main Entity (Co-occurrence)
            if entity_node.id != main_node.id:
                self.add_edge(main_node, entity_node, "co_occurs_with", 0.9)
                self.add_edge(entity_node, main_node, "co_occurs_with", 0.9)
                
                # Also link to the source if we have context? 
                # EYE-D flat entities list makes it hard to map back to specific source result
                # We'll skip source linking for extracted entities for now to avoid noise
                
        # 4. Bulk upsert (avoid clobbering embedded edges)
        index_name = self._get_index_name()

        success, errors = self._bulk_upsert_nodes(list(nodes_to_index.values()), index_name)
        
        if errors:
            logger.warning(f"Indexing errors: {len(errors)}")
            
        self.es.indices.refresh(index=index_name)
        
        return {
            "index": index_name,
            "total_nodes": success,
            "errors": len(errors) if errors else 0,
            "main_entity": query_value
        }

    def get_node(self, node_id: str) -> Optional[Dict]:
        """Get a node by ID."""
        index_name = self._get_index_name()
        try:
            result = self.es.get(index=index_name, id=node_id)
            return result["_source"]
        except:
            return None
    
    def search_nodes(
        self,
        query: str,
        node_class: str = None,
        node_type: str = None,
        limit: int = 20
    ) -> List[Dict]:
        """Search nodes by label."""
        index_name = self._get_index_name()
        
        es_query = {
            "bool": {
                "must": [
                    {"match": {"label": query}}
                ]
            }
        }
        
        if node_class:
            es_query["bool"]["filter"] = es_query["bool"].get("filter", [])
            es_query["bool"]["filter"].append({"term": {"node_class": node_class}})
        
        if node_type:
            es_query["bool"]["filter"] = es_query["bool"].get("filter", [])
            es_query["bool"]["filter"].append({"term": {"type": node_type}})
        
        result = self.es.search(
            index=index_name,
            body={"query": es_query, "size": limit}
        )
        
        return [hit["_source"] for hit in result["hits"]["hits"]]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get index statistics."""
        index_name = self._get_index_name()
        
        if not self.es.indices.exists(index=index_name):
            return {"exists": False}
        
        total = self.es.count(index=index_name)["count"]
        
        stats = {
            "exists": True,
            "index": index_name,
            "total_nodes": total,
            "by_class": {},
            "by_type": {}
        }
        
        # Count by class
        for cls in ["entity", "source"]:
            count = self.es.count(
                index=index_name,
                body={"query": {"term": {"node_class": cls}}}
            )["count"]
            stats["by_class"][cls] = count
        
        # Count by type
        for typ in ["person", "company", "email", "domain", "webpage"]:
            count = self.es.count(
                index=index_name,
                body={"query": {"term": {"type": typ}}}
            )["count"]
            if count > 0:
                stats["by_type"][typ] = count
        
        return stats


# CLI
if __name__ == "__main__":
    import argparse
    import asyncio
    
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    
    parser = argparse.ArgumentParser(description="LINKLATER C-1 Bridge")
    parser.add_argument("--project", "-p", help="Project ID")
    parser.add_argument("--stats", action="store_true", help="Show index stats")
    parser.add_argument("--test", action="store_true", help="Run test indexing")
    
    args = parser.parse_args()
    
    bridge = C1Bridge(project_id=args.project)
    
    if args.stats:
        stats = bridge.get_stats()
        print(json.dumps(stats, indent=2))
    
    elif args.test:
        # Test with mock CLINK results
        mock_results = {
            "related_sites": [
                {
                    "url": "https://en.wikipedia.org/wiki/Satya_Nadella",
                    "domain": "en.wikipedia.org",
                    "title": "Satya Nadella - Wikipedia",
                    "matched_entities": ["Satya Nadella", "Microsoft"]
                },
                {
                    "url": "https://www.forbes.com/profile/satya-nadella/",
                    "domain": "forbes.com",
                    "title": "Satya Nadella",
                    "matched_entities": ["Satya Nadella", "Microsoft"]
                }
            ],
            "combo_results": {
                "Satya Nadella + Microsoft": 2
            },
            "stats": {}
        }
        
        stats = bridge.index_clink_results(mock_results)
        print(f"\nIndexed to {stats['index']}:")
        print(f"  Entities: {stats['entities_indexed']}")
        print(f"  Sources: {stats['sources_indexed']}")
        print(f"  Total: {stats['total_nodes']}")
        
        # Show stats
        print("\nIndex stats:")
        print(json.dumps(bridge.get_stats(), indent=2))
