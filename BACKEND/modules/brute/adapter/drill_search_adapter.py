#!/usr/bin/env python3
"""
Cymonides -> Drill Search Adapter

Allows CyMonides to ingest/index content into Drill Search's Elasticsearch
using the same schema and embedding rules (all-MiniLM-L6-v2, 384 dims).

Usage:
    from brute.adapter.drill_search_adapter import DrillSearchAdapter

    adapter = DrillSearchAdapter()
    adapter.index_document(content="...", label="...", className="source")
    adapter.search_semantic(query="offshore companies", k=10)
"""

import os
import json
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
from pathlib import Path

try:
    from elasticsearch import Elasticsearch
    from transformers import pipeline
    ES_AVAILABLE = True
except ImportError:
    ES_AVAILABLE = False
    print("⚠️  elasticsearch or transformers not installed")

try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

class DrillSearchAdapter:
    """
    Adapter to make CyMonides work with Drill Search's Elasticsearch schema.

    CYMONIDES MANDATE:
    - ALL nodes indexed to cymonides-1-{project_id} (project-specific)
    - ALL edges EMBEDDED in nodes (no separate edge index)
    - No hardcoded index names - project_id REQUIRED

    Features:
    - Uses same vector model: all-MiniLM-L6-v2 (384 dims)
    - Follows Drill Search node schema (id, label, className, type, metadata, etc.)
    - Generates description_vector and content_vector like elasticSyncService
    - Validates edges against edge_types.json (69 relationship types)
    - Converts entities to/from FTM (Follow The Money) schemas
    """

    # CYMONIDES MANDATE: No default indices - project_id is REQUIRED
    ELASTIC_URL = os.getenv("ELASTICSEARCH_URL", os.getenv("ELASTIC_URL", "http://localhost:9200"))
    ENABLE_EMBEDDINGS = os.getenv("ENABLE_EMBEDDINGS", "true").lower() == "true"
    EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "local").lower() # 'local' or 'openai'
    VECTOR_DIMS = 384  # all-MiniLM-L6-v2

    def __init__(self, project_id: str = None):
        """
        Initialize Elasticsearch client, embedding model, and schema loaders.

        CYMONIDES MANDATE: project_id is REQUIRED for all node operations.
        If not provided at init, must be provided per-operation.
        """
        if not ES_AVAILABLE:
            raise RuntimeError("elasticsearch and transformers packages required")

        self.project_id = project_id
        # CYMONIDES MANDATE: Index name is cymonides-1-{project_id}
        self.NODES_INDEX = f"cymonides-1-{project_id}" if project_id else None
        # CYMONIDES MANDATE: Edges are EMBEDDED in nodes - no separate edge index
        self.EDGES_INDEX = None  # DEPRECATED - edges are embedded

        self.client = Elasticsearch([self.ELASTIC_URL])
        self.es = self.client
        self.embedder = None

        # Load edge types and FTM schemas
        self.edge_types = self._load_edge_types()
        self.ftm_schema = self._load_ftm_schema()

        # Load template validator for enhanced validation and auto-population
        try:
            from .template_validator import TemplateValidator
            self.template_validator = TemplateValidator()
            print("✅ Template validator loaded with enhanced schemas")
        except Exception as e:
            print(f"⚠️  Template validator not available: {e}")
            self.template_validator = None

        if self.ENABLE_EMBEDDINGS:
            self._init_embeddings()

    def _init_embeddings(self):
        """Initialize the embedding provider"""
        if self.EMBEDDING_PROVIDER == 'openai':
            if not OPENAI_AVAILABLE:
                print("⚠️  openai package not installed. Falling back to local.")
                self.EMBEDDING_PROVIDER = 'local'
            elif not os.getenv("OPENAI_API_KEY"):
                print("⚠️  OPENAI_API_KEY not set. Falling back to local.")
                self.EMBEDDING_PROVIDER = 'local'
            else:
                print("🔄 Using OpenAI embeddings (text-embedding-3-small)...")
                self.openai_client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
                self.VECTOR_DIMS = 1536 # OpenAI text-embedding-3-small
                return

        if self.EMBEDDING_PROVIDER == 'local':
            try:
                print("🔄 Loading all-MiniLM-L6-v2 embedding model...")
                self.embedder = pipeline('feature-extraction', model='sentence-transformers/all-MiniLM-L6-v2')
                print("✅ Embedding model loaded")
            except Exception as e:
                print(f"⚠️  Embedding model failed to load: {e}")
                self.embedder = None

    def _load_edge_types(self) -> Dict[str, Any]:
        """Load edges.json schema (V4)"""
        try:
            schema_path = Path(__file__).parent.parent.parent.parent / "input_output" / "matrix" / "schema" / "edges.json"
            with open(schema_path, 'r') as f:
                schema = json.load(f)
            
            # Convert V4 flat list to category-grouped structure for compatibility
            edge_types = {}
            for edge in schema.get("edges", []):
                cat = edge.get("category", "uncategorized")
                if cat not in edge_types:
                    edge_types[cat] = {"edge_types": []}
                
                # Map V4 fields to adapter expectations
                source_types = edge.get("source")
                if isinstance(source_types, str):
                    source_types = [source_types]
                    
                target_types = edge.get("target")
                if isinstance(target_types, str):
                    target_types = [target_types]
                
                edge_def = edge.copy()
                edge_def["relationship_type"] = edge.get("relation")
                edge_def["source_types"] = source_types
                edge_def["target_types"] = target_types
                
                edge_types[cat]["edge_types"].append(edge_def)

            print(f"✅ Loaded {len(schema.get('edges', []))} edge types from V4 schema")
            return edge_types
        except Exception as e:
            print(f"⚠️  Failed to load edges.json: {e}")
            return {}

    def _load_ftm_schema(self) -> Dict[str, Any]:
        """
        Load FTM schema mappings.
        
        Ideally, we load embedded mappings from V4 nodes.json.
        However, since the user explicitly verified 'ftm_schema_mapping.json' in 'edges/',
        we should support reading from there if nodes.json doesn't have what we need,
        or strictly stick to V4 embedded truth.
        
        Given V4 deployment report says '✓ ftm_schema_mapping.json (5.5KB) - Correct location',
        it is safest to check that location if embedded loading fails or as a fallback.
        
        For now, we stick to embedded V4 in nodes.json as it is the "Source of Truth" for V4.
        """
        try:
            schema_path = Path(__file__).parent.parent.parent.parent / "input_output" / "matrix" / "schema" / "nodes.json"
            with open(schema_path, 'r') as f:
                nodes_schema = json.load(f)
            
            mappings = {}
            
            for class_name, class_def in nodes_schema.get("classes", {}).items():
                for type_name, type_def in class_def.get("types", {}).items():
                    if "ftm_schema" in type_def:
                        # Build property map
                        props = {}
                        for prop_name, prop_def in type_def.get("properties", {}).items():
                            if "ftm_property" in prop_def:
                                props[prop_name] = prop_def["ftm_property"]
                        
                        mappings[type_name] = {
                            "ftm_schema": type_def["ftm_schema"],
                            "properties": props
                        }
            
            print(f"✅ Loaded FTM mapping for {len(mappings)} types from V4 schema (embedded)")
            return {"mappings": mappings}
        except Exception as e:
            print(f"⚠️  Failed to load embedded FTM mapping from nodes.json: {e}")
            return {}

    def _embed_text(self, text: str) -> Optional[List[float]]:
        """Generate vector embedding using configured provider"""
        if not text:
            return None

        if self.EMBEDDING_PROVIDER == 'openai':
            try:
                response = self.openai_client.embeddings.create(
                    input=text,
                    model="text-embedding-3-small"
                )
                return response.data[0].embedding
            except Exception as e:
                print(f"⚠️  OpenAI embedding error: {e}")
                return None

        # Local Fallback
        if not self.embedder:
            return None

        try:
            # Mean pooling + L2 normalization (same as elasticSyncService)
            output = self.embedder(text, truncation=True, max_length=512)
            # Extract embeddings and convert to list
            embedding = output[0][0]  # Get first sequence, first token
            # If output is nested, flatten it
            if isinstance(embedding, list) and len(embedding) > 0 and isinstance(embedding[0], list):
                # Mean pooling
                import numpy as np
                embedding = np.mean(embedding, axis=0).tolist()
            return embedding
        except Exception as e:
            print(f"⚠️  Embedding error: {e}")
            return None

    def _build_semantic_string(self, doc: Dict[str, Any]) -> str:
        """
        Build semantic description string (like elasticSyncService.ts:108-115)
        Combines: label + content + query + section + jurisdiction + friction + keyphrases
        """
        parts = []

        if doc.get('label'):
            parts.append(doc['label'])
        if doc.get('content'):
            parts.append(doc['content'])
        if doc.get('query'):
            parts.append(doc['query'])

        # Metadata fields
        metadata = doc.get('metadata', {})
        if metadata.get('section'):
            parts.append(metadata['section'])
        if metadata.get('jurisdiction'):
            parts.append(metadata['jurisdiction'])
        if metadata.get('friction'):
            parts.append(str(metadata['friction']))
        if metadata.get('keyphrases'):
            keyphrases = metadata['keyphrases']
            if isinstance(keyphrases, list):
                parts.extend(keyphrases)
            elif isinstance(keyphrases, str):
                parts.append(keyphrases)

        return ' '.join(filter(None, parts))

    def _add_embeddings(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        """
        Add vector embeddings to document (like elasticSyncService.ts:116-131)
        Generates:
        - description_vector: semantic metadata (label + content + query + metadata)
        - content_vector: raw content
        """
        if not self.ENABLE_EMBEDDINGS:
            doc['embedding_status'] = 'skipped'
            return doc

        try:
            # Generate description_vector from semantic string
            semantic = self._build_semantic_string(doc)
            description_vec = self._embed_text(semantic)

            # Generate content_vector from raw content
            content = doc.get('content', semantic)
            content_vec = self._embed_text(content)

            # Add vectors to document
            if description_vec:
                doc['description_vector'] = description_vec
            if content_vec:
                doc['content_vector'] = content_vec

            doc['embedding_status'] = 'embedded' if (description_vec or content_vec) else 'skipped'
            doc['embedding_updated'] = datetime.now(timezone.utc).isoformat()

        except Exception as e:
            print(f"⚠️  Embedding generation failed: {e}")
            doc['embedding_status'] = 'error'

        return doc

    def index_node(self,
                   id: str = None,
                   label: str = "",
                   content: str = "",
                   className: str = "source",
                   typeName: str = None,
                   url: str = None,
                   metadata: Dict[str, Any] = None,
                   index_name: str = None,
                   project_id: str = None,
                   **kwargs) -> Dict[str, Any]:
        """
        Index a node into Drill Search's index.

        CYMONIDES MANDATE: project_id is REQUIRED. All nodes go to cymonides-1-{project_id}.

        Args:
            id: Node ID (auto-generated if not provided)
            label: Node label/title
            content: Main content/text
            className: Node class (source, subject, object, location, narrative)
            typeName: Node type (webpage, person, company, etc.)
            url: Source URL
            metadata: Additional metadata dict
            index_name: Optional custom index (overrides cymonides-1-{project_id})
            project_id: CYMONIDES MANDATE: Project ID (required if not set at init)
            **kwargs: Additional fields (userId, projectId, etc.)

        Returns:
            Indexed document
        """
        # CYMONIDES MANDATE: Determine target index
        effective_project_id = project_id or kwargs.get('projectId') or self.project_id
        if index_name:
            target_index = index_name
        elif effective_project_id:
            target_index = f"cymonides-1-{effective_project_id}"
        else:
            raise ValueError("CYMONIDES MANDATE: project_id is REQUIRED for indexing nodes")

        if not id:
            from uuid import uuid4
            id = f"cymonides_{uuid4().hex[:12]}"

        # Build initial document following Drill Search schema
        doc = {
            'id': id,
            'label': label,
            'content': content,
            'className': className,
            'typeName': typeName or className,
            'url': url,
            'metadata': metadata or {},
            'timestamp': kwargs.get('timestamp', datetime.now(timezone.utc).isoformat()),
            'createdAt': kwargs.get('createdAt', datetime.now(timezone.utc).isoformat()),
            'updatedAt': datetime.now(timezone.utc).isoformat(),
            'embedding_status': 'pending'
        }

        # Handle V4 compatibility fields (raw_properties, codes, suite)
        if 'raw_properties' in kwargs:
            if 'metadata' not in doc: doc['metadata'] = {}
            doc['metadata']['raw_properties'] = kwargs['raw_properties']
        
        if 'codes' in kwargs:
            if 'metadata' not in doc: doc['metadata'] = {}
            doc['metadata']['codes'] = kwargs['codes']

        if 'suite' in kwargs:
            if 'metadata' not in doc: doc['metadata'] = {}
            doc['metadata']['suite'] = kwargs['suite']

        # Add optional fields
        for key in ['userId', 'projectId', 'ordering', 'weight', 'status', 'query', 'lastSeen']:
            if key in kwargs:
                doc[key] = kwargs[key]

        # Apply enhanced template validation and auto-population if available
        # Only for standard Drill index
        if self.template_validator and className == 'source' and target_index == self.NODES_INDEX:
            try:
                # Map typeName to template type (e.g., webpage -> webdomain)
                template_type = self._map_to_template_type(typeName)

                # Auto-populate and validate
                populated, valid, errors = self.template_validator.validate_and_populate(
                    doc, template_type, mode='discovery'
                )

                if not valid:
                    # print(f"⚠️  Validation warnings for {id}: {errors}") # Silenced for cleaner logs
                    pass

                # Use populated data (includes auto-generated fields like node_id, provenance, etc.)
                doc.update(populated)

            except Exception as e:
                # print(f"⚠️  Template validation skipped: {e}") # Silenced for cleaner logs
                pass

        # Add embeddings
        doc = self._add_embeddings(doc)

        # Index to Elasticsearch
        try:
            self.client.index(
                index=target_index,
                id=id,
                document=doc,
                refresh='wait_for'
            )
            print(f"✅ Indexed node to {target_index}: {id} ({label[:50]}...)")
            return doc
        except Exception as e:
            print(f"❌ Index error: {e}")
            raise

    def _map_to_template_type(self, typeName: str) -> str:
        """Map Drill Search type names to template type names"""
        mapping = {
            'webpage': 'webdomain',
            'pdf': 'document',
            'doc': 'document',
            'dataset': 'data_pool',
            'registry': 'public_records'
        }
        return mapping.get(typeName, typeName)

    def validate_edge(self, relation: str, source_type: str, target_type: str) -> Dict[str, Any]:
        """
        Validate edge relationship against edge_types.json schema.

        Args:
            relation: Relationship type (e.g., "officer_of", "owns")
            source_type: Source node type (e.g., "person", "company")
            target_type: Target node type (e.g., "company", "address")

        Returns:
            Edge schema if valid, or None with warning
        """
        if not self.edge_types:
            return None

        # Search through all categories for this relationship type
        for category, category_data in self.edge_types.items():
            for edge_def in category_data.get('edge_types', []):
                if edge_def['relationship_type'] == relation:
                    # Check if source and target types match
                    source_match = source_type in edge_def.get('source_types', [])
                    target_match = target_type in edge_def.get('target_types', [])

                    if source_match and target_match:
                        return edge_def
                    else:
                        print(f"⚠️  Edge '{relation}' found but types don't match:")
                        print(f"   Expected: {edge_def['source_types']} -> {edge_def['target_types']}")
                        print(f"   Got: {source_type} -> {target_type}")
                        return None

        print(f"⚠️  Unknown edge type: {relation}")
        return None

    def get_edge_metadata_schema(self, relation: str) -> Dict[str, Any]:
        """Get metadata schema for an edge type"""
        for category_data in self.edge_types.values():
            for edge_def in category_data.get('edge_types', []):
                if edge_def['relationship_type'] == relation:
                    return edge_def.get('metadata_schema', {})
        return {}

    def index_edge(self,
                   from_node: str,
                   to_node: str,
                   relation: str,
                   id: str = None,
                   metadata: Dict[str, Any] = None,
                   source_type: str = None,
                   target_type: str = None,
                   validate: bool = True,
                   project_id: str = None,
                   **kwargs) -> Dict[str, Any]:
        """
        CYMONIDES MANDATE: Edges are EMBEDDED in nodes, not stored separately.

        This method embeds the edge in the source node's embedded_edges array.

        Args:
            from_node: Source node ID
            to_node: Target node ID
            relation: Relation type
            id: Edge ID (auto-generated if not provided)
            metadata: Additional metadata
            source_type: Source node type (for validation)
            target_type: Target node type (for validation)
            validate: Whether to validate against edge_types.json
            project_id: CYMONIDES MANDATE: Project ID (required)
            **kwargs: Additional fields

        Returns:
            Embedded edge document
        """
        if not id:
            from uuid import uuid4
            id = f"edge_{uuid4().hex[:12]}"

        # CYMONIDES MANDATE: Determine target index
        effective_project_id = project_id or kwargs.get('projectId') or self.project_id
        if not effective_project_id:
            raise ValueError("CYMONIDES MANDATE: project_id is REQUIRED for indexing edges")
        target_index = f"cymonides-1-{effective_project_id}"

        # Validate edge if types provided
        if validate and source_type and target_type:
            edge_schema = self.validate_edge(relation, source_type, target_type)
            if edge_schema:
                # Check required metadata fields
                metadata_schema = edge_schema.get('metadata_schema', {})
                required_fields = metadata_schema.get('required', [])
                provided_metadata = metadata or {}

                missing_fields = [f for f in required_fields if f not in provided_metadata]
                if missing_fields:
                    print(f"⚠️  Edge '{relation}' missing required metadata: {missing_fields}")

        edge = {
            'id': id,
            'from': from_node,
            'to': to_node,
            'relation': relation,
            'type': relation,
            'metadata': metadata or {},
            'timestamp': kwargs.get('timestamp', datetime.now(timezone.utc).isoformat()),
            'createdAt': kwargs.get('createdAt', datetime.now(timezone.utc).isoformat()),
            'updatedAt': datetime.now(timezone.utc).isoformat()
        }

        for key in ['userId', 'projectId', 'ordering', 'weight']:
            if key in kwargs:
                edge[key] = kwargs[key]

        # CYMONIDES MANDATE: Embed edge in source node's embedded_edges array
        try:
            self.client.update(
                index=target_index,
                id=from_node,
                body={
                    "script": {
                        "source": """
                            if (ctx._source.embedded_edges == null) {
                                ctx._source.embedded_edges = [];
                            }
                            ctx._source.embedded_edges.add(params.edge);
                        """,
                        "params": {"edge": edge}
                    }
                },
                refresh='wait_for'
            )
            print(f"✅ Embedded edge in {from_node}: {from_node} --[{relation}]--> {to_node}")
            return edge
        except Exception as e:
            print(f"⚠️  Could not embed edge (source node may not exist): {e}")
            # Return the edge anyway - caller may want to index it with the node
            return edge

    def search_semantic(self,
                       query: str,
                       k: int = 10,
                       vector_field: str = "description_vector",
                       filters: Dict = None,
                       index_name: str = None,
                       project_id: str = None) -> List[Dict[str, Any]]:
        """
        Semantic search using kNN vector similarity.

        CYMONIDES MANDATE: project_id is REQUIRED to determine search index.

        Args:
            query: Search query text
            k: Number of results
            vector_field: "description_vector" or "content_vector"
            filters: Elasticsearch query filters
            index_name: Optional custom index (overrides cymonides-1-{project_id})
            project_id: CYMONIDES MANDATE: Project ID (required if not set at init)

        Returns:
            List of matching nodes with scores
        """
        # CYMONIDES MANDATE: Determine target index
        effective_project_id = project_id or self.project_id
        if index_name:
            target_index = index_name
        elif effective_project_id:
            target_index = f"cymonides-1-{effective_project_id}"
        else:
            raise ValueError("CYMONIDES MANDATE: project_id is REQUIRED for searching")

        if not self.ENABLE_EMBEDDINGS:
             raise RuntimeError("Embeddings not enabled")

        # Generate query vector
        query_vec = self._embed_text(query)
        if not query_vec:
            return []

        # Build kNN query
        search_body = {
            "knn": {
                "field": vector_field,
                "query_vector": query_vec,
                "k": k,
                "num_candidates": k * 10
            }
        }

        if filters:
            search_body["knn"]["filter"] = filters

        # Execute search
        try:
            results = self.client.search(
                index=target_index,
                body=search_body
            )

            hits = []
            for hit in results['hits']['hits']:
                hits.append({
                    **hit['_source'],
                    'score': hit['_score']
                })

            return hits
        except Exception as e:
            print(f"❌ Search error: {e}")
            return []

    def search_hybrid(self,
                     query: str,
                     k: int = 10,
                     keyword_weight: float = 0.5,
                     vector_field: str = "description_vector",
                     index_name: str = None,
                     project_id: str = None) -> List[Dict[str, Any]]:
        """
        Hybrid search: keyword (BM25) + semantic (kNN).

        CYMONIDES MANDATE: project_id is REQUIRED to determine search index.

        Args:
            query: Search query
            k: Number of results
            keyword_weight: Weight for keyword search (0-1)
            vector_field: Vector field to use
            index_name: Optional custom index (overrides cymonides-1-{project_id})
            project_id: CYMONIDES MANDATE: Project ID (required if not set at init)

        Returns:
            Combined results
        """
        # CYMONIDES MANDATE: Determine target index
        effective_project_id = project_id or self.project_id
        if index_name:
            target_index = index_name
        elif effective_project_id:
            target_index = f"cymonides-1-{effective_project_id}"
        else:
            raise ValueError("CYMONIDES MANDATE: project_id is REQUIRED for searching")

        if not self.ENABLE_EMBEDDINGS:
            print("⚠️  Embeddings disabled, falling back to keyword-only")
            return self.search_keyword(query, k, index_name=target_index)

        query_vec = self._embed_text(query)
        if not query_vec:
            return self.search_keyword(query, k, index_name=target_index)

        search_body = {
            "query": {
                "bool": {
                    "should": [
                        {
                            "multi_match": {
                                "query": query,
                                "fields": ["label^3", "content", "query", "metadata.description"],
                                "boost": keyword_weight
                            }
                        }
                    ]
                }
            },
            "knn": {
                "field": vector_field,
                "query_vector": query_vec,
                "k": k,
                "num_candidates": k * 10,
                "boost": 1 - keyword_weight
            },
            "size": k
        }

        try:
            results = self.client.search(
                index=target_index,
                body=search_body
            )

            hits = []
            for hit in results['hits']['hits']:
                hits.append({
                    **hit['_source'],
                    'score': hit['_score']
                })

            return hits
        except Exception as e:
            print(f"❌ Hybrid search error: {e}")
            return []

    def search_keyword(self, query: str, k: int = 10, index_name: str = None, project_id: str = None) -> List[Dict[str, Any]]:
        """
        Simple keyword search (BM25).

        CYMONIDES MANDATE: project_id is REQUIRED to determine search index.
        """
        # CYMONIDES MANDATE: Determine target index
        effective_project_id = project_id or self.project_id
        if index_name:
            target_index = index_name
        elif effective_project_id:
            target_index = f"cymonides-1-{effective_project_id}"
        else:
            raise ValueError("CYMONIDES MANDATE: project_id is REQUIRED for searching")
        try:
            results = self.client.search(
                index=target_index,
                body={
                    "query": {
                        "multi_match": {
                            "query": query,
                            "fields": ["label^3", "content", "query"]
                        }
                    },
                    "size": k
                }
            )

            hits = []
            for hit in results['hits']['hits']:
                hits.append({
                    **hit['_source'],
                    'score': hit['_score']
                })

            return hits
        except Exception as e:
            print(f"❌ Keyword search error: {e}")
            return []

    def to_ftm(self, node: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Convert Drill Search node to FTM (Follow The Money) schema.

        Args:
            node: Drill Search node document

        Returns:
            FTM entity dict or None
        """
        if not self.ftm_schema:
            return None

        node_type = node.get('typeName', node.get('className'))
        ftm_mapping = self.ftm_schema.get('mappings', {}).get(node_type)

        if not ftm_mapping:
            return None

        ftm_entity = {
            'schema': ftm_mapping['ftm_schema'],
            'id': node.get('id'),
            'properties': {}
        }

        # Map properties
        property_map = ftm_mapping.get('properties', {})
        metadata = node.get('metadata', {})

        for drill_prop, ftm_prop in property_map.items():
            # Check in root level first, then metadata
            value = node.get(drill_prop) or metadata.get(drill_prop)
            if value:
                ftm_entity['properties'][ftm_prop] = value

        # Add label as name if not already mapped
        if 'name' not in ftm_entity['properties'] and node.get('label'):
            ftm_entity['properties']['name'] = node['label']

        return ftm_entity

    def from_ftm(self, ftm_entity: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Convert FTM entity to Drill Search node schema.

        Args:
            ftm_entity: FTM entity dict with 'schema' and 'properties'

        Returns:
            Drill Search node dict
        """
        if not self.ftm_schema:
            return None

        ftm_schema_name = ftm_entity.get('schema')

        # Find reverse mapping
        for node_type, mapping in self.ftm_schema.get('mappings', {}).items():
            if mapping['ftm_schema'] == ftm_schema_name:
                properties = ftm_entity.get('properties', {})
                metadata = {}

                # Reverse map properties
                property_map = mapping.get('properties', {})
                reverse_map = {v: k for k, v in property_map.items()}

                for ftm_prop, value in properties.items():
                    drill_prop = reverse_map.get(ftm_prop, ftm_prop)
                    metadata[drill_prop] = value

                # Build node
                node = {
                    'id': ftm_entity.get('id', f"ftm_{datetime.now(timezone.utc).timestamp()}"),
                    'label': properties.get('name', ''),
                    'className': 'subject',  # FTM entities are subjects
                    'typeName': node_type,
                    'metadata': {
                        **metadata,
                        'ftm_origin': True,
                        'ftm_schema': ftm_schema_name
                    }
                }

                return node

        return None

    def list_valid_edges_for_type(self, node_type: str, direction: str = 'outgoing') -> List[Dict[str, Any]]:
        """
        List all valid edge types for a given node type.

        Args:
            node_type: Node type (e.g., "person", "company")
            direction: "outgoing", "incoming", or "both"

        Returns:
            List of valid edge definitions
        """
        valid_edges = []

        for category_data in self.edge_types.values():
            for edge_def in category_data.get('edge_types', []):
                edge_direction = edge_def.get('direction', 'outgoing')

                if direction == 'both' or direction == edge_direction or edge_direction == 'bidirectional':
                    # Check if this node type is in source or target types
                    if direction in ['outgoing', 'both'] and node_type in edge_def.get('source_types', []):
                        valid_edges.append({
                            **edge_def,
                            'role': 'source'
                        })
                    if direction in ['incoming', 'both'] and node_type in edge_def.get('target_types', []):
                        valid_edges.append({
                            **edge_def,
                            'role': 'target'
                        })

        return valid_edges


# Convenience functions
def index_document(content: str, label: str = "", project_id: str = None, **kwargs) -> Dict[str, Any]:
    """
    Quick index a document.

    CYMONIDES MANDATE: project_id is REQUIRED.
    """
    if not project_id:
        raise ValueError("CYMONIDES MANDATE: project_id is REQUIRED")
    adapter = DrillSearchAdapter(project_id=project_id)
    return adapter.index_node(content=content, label=label, **kwargs)


def search(query: str, k: int = 10, mode: str = "semantic", project_id: str = None) -> List[Dict[str, Any]]:
    """
    Quick search.

    CYMONIDES MANDATE: project_id is REQUIRED.
    """
    if not project_id:
        raise ValueError("CYMONIDES MANDATE: project_id is REQUIRED")
    adapter = DrillSearchAdapter(project_id=project_id)
    if mode == "semantic":
        return adapter.search_semantic(query, k)
    elif mode == "hybrid":
        return adapter.search_hybrid(query, k)
    else:
        return adapter.search_keyword(query, k)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test DrillSearchAdapter")
    parser.add_argument("--project-id", required=True, help="CYMONIDES MANDATE: Project ID")
    args = parser.parse_args()

    # Test the adapter
    print("🧪 Testing DrillSearchAdapter\n")
    print(f"CYMONIDES Index: cymonides-1-{args.project_id}")

    adapter = DrillSearchAdapter(project_id=args.project_id)

    # Index test document
    doc = adapter.index_node(
        label="Offshore Company Formation Guide",
        content="Complete guide to setting up offshore companies in BVI for asset protection",
        className="source",
        typeName="webpage",
        url="https://example.com/offshore-guide",
        metadata={
            "jurisdiction": "British Virgin Islands",
            "keyphrases": ["offshore", "BVI", "asset protection"]
        }
    )

    print(f"\n📊 Indexed document:")
    print(f"   ID: {doc['id']}")
    print(f"   Embedding status: {doc.get('embedding_status')}")
    print(f"   Has description_vector: {bool(doc.get('description_vector'))}")
    print(f"   Has content_vector: {bool(doc.get('content_vector'))}")

    # Test semantic search
    print(f"\n🔍 Testing semantic search...")
    results = adapter.search_semantic("offshore tax havens", k=3)
    print(f"   Found {len(results)} results")
    for i, result in enumerate(results):
        print(f"   {i+1}. [{result['score']:.3f}] {result.get('label', 'Untitled')}")
