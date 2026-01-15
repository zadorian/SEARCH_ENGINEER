"""
CyMonides 2.0 - Elasticsearch Backend
Unified backend supporting:
- Knowledge graph (entities, relations, observations)
- Document indexing (full-text + semantic)
- Hybrid search (BM25 + kNN)
"""

from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk
from typing import Dict, Any, List, Optional
import json
from datetime import datetime
from loguru import logger

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from config.unified_config import config


class ElasticsearchBackend:
    """
    Elasticsearch backend for CyMonides 2.0

    Features:
    - Unified index for entities, relations, observations, documents
    - BM25 keyword search
    - kNN vector search
    - Hybrid search
    - Graph traversal
    """

    # Unified Schema Mapping
    UNIFIED_SCHEMA = {
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 1,
            "analysis": {
                "analyzer": {
                    "custom_text_analyzer": {
                        "type": "custom",
                        "tokenizer": "standard",
                        "filter": ["lowercase", "stop", "snowball"]
                    }
                }
            }
        },
        "mappings": {
            "properties": {
                # === UNIVERSAL FIELDS ===
                "id": {"type": "keyword"},
                "doc_type": {
                    "type": "keyword"  # "entity", "document", "relation", "observation"
                },
                "zone_id": {"type": "keyword"},
                "created_at": {"type": "date"},
                "updated_at": {"type": "date"},
                "last_accessed": {"type": "date"},
                "access_count": {"type": "integer"},
                "relevance_score": {"type": "float"},

                # === ENTITY FIELDS (Nexus Graph) ===
                "entity_type": {
                    "type": "keyword"  # "person", "company", "location", "concept"
                },
                "entity_name": {
                    "type": "text",
                    "fields": {"keyword": {"type": "keyword"}},
                    "analyzer": "custom_text_analyzer"
                },
                "relations": {
                    "type": "nested",
                    "properties": {
                        "relation_type": {"type": "keyword"},
                        "target_entity_id": {"type": "keyword"},
                        "target_entity_name": {"type": "text"},
                        "confidence": {"type": "float"},
                        "created_at": {"type": "date"},
                        "metadata": {"type": "object", "enabled": True}
                    }
                },
                "observations": {
                    "type": "nested",
                    "properties": {
                        "text": {"type": "text", "analyzer": "custom_text_analyzer"},
                        "relevance": {"type": "float"},
                        "created_at": {"type": "date"},
                        "source": {"type": "keyword"}
                    }
                },

                # === DOCUMENT FIELDS (CyMonides) ===
                "title": {"type": "text", "analyzer": "custom_text_analyzer"},
                "content": {"type": "text", "analyzer": "custom_text_analyzer"},
                "file_path": {"type": "keyword"},
                "file_type": {"type": "keyword"},
                "schema_type": {"type": "keyword"},
                "extracted_metadata": {"type": "object", "enabled": True},
                "extracted_entities": {"type": "keyword"},  # Array of entity IDs

                # === VECTOR FIELDS (Semantic Search) ===
                "content_vector": {
                    "type": "dense_vector",
                    "dims": config.VECTOR_DIMENSIONS,
                    "index": True,
                    "similarity": config.VECTOR_SIMILARITY
                },
                "schema_vector": {
                    "type": "dense_vector",
                    "dims": config.VECTOR_DIMENSIONS,
                    "index": True,
                    "similarity": config.VECTOR_SIMILARITY
                },
                "metadata_vector": {
                    "type": "dense_vector",
                    "dims": config.VECTOR_DIMENSIONS,
                    "index": True,
                    "similarity": config.VECTOR_SIMILARITY
                },

                # === CONTENT INVENTORY FIELDS ===
                "available_fields": {"type": "keyword"},
                "country": {"type": "keyword"},
                "date_range": {"type": "date_range"},
                "size": {"type": "integer"},
                "format": {"type": "keyword"},
                "tags": {"type": "keyword"},
                "processed_by": {"type": "keyword"},
                "available_for": {"type": "keyword"},

                # === USAGE TRACKING ===
                "use_count": {"type": "integer"},
                "common_next_actions": {"type": "keyword"},

                # === BACKUP TRACKING ===
                "indexed_in_whoosh": {"type": "boolean"},
                "whoosh_index_name": {"type": "keyword"}
            }
        }
    }

    def __init__(self):
        """Initialize Elasticsearch connection"""
        self.client = Elasticsearch(**config.get_elasticsearch_config())
        self.index_name = config.ELASTICSEARCH_INDEX
        self._ensure_index()

    def _ensure_index(self):
        """Create unified index if it doesn't exist"""
        try:
            if not self.client.indices.exists(index=self.index_name):
                logger.info(f"Creating Elasticsearch index: {self.index_name}")
                self.client.indices.create(
                    index=self.index_name,
                    body=self.UNIFIED_SCHEMA
                )
                logger.success(f"✓ Created index: {self.index_name}")
            else:
                logger.info(f"Index {self.index_name} already exists")
        except Exception as e:
            logger.error(f"Failed to create index: {e}")
            raise

    def ping(self) -> bool:
        """Check if Elasticsearch is accessible"""
        try:
            return self.client.ping()
        except Exception as e:
            return False

    # === ENTITY OPERATIONS ===

    def index_entity(self, entity: Dict[str, Any]) -> Dict[str, Any]:
        """
        Index a knowledge graph entity

        Args:
            entity: Entity data with fields:
                - entity_name: Name of entity
                - entity_type: Type (person, company, etc.)
                - zone_id: Memory zone
                - observations: List of observations (optional)
                - relations: List of relations (optional)

        Returns:
            {"id": entity_id, "backend": "elasticsearch"}
        """
        entity["doc_type"] = "entity"
        entity["created_at"] = datetime.utcnow().isoformat()
        entity["updated_at"] = entity["created_at"]
        entity["access_count"] = 0
        entity["use_count"] = 0

        # Set default zone
        if "zone_id" not in entity:
            entity["zone_id"] = config.DEFAULT_ZONE

        # Initialize empty arrays if not provided
        if "observations" not in entity:
            entity["observations"] = []
        if "relations" not in entity:
            entity["relations"] = []

        try:
            response = self.client.index(
                index=self.index_name,
                document=entity,
                refresh=True
            )

            entity_id = response["_id"]
            logger.success(f"✓ Indexed entity: {entity.get('entity_name')} ({entity_id})")

            return {"id": entity_id, "backend": "elasticsearch"}

        except Exception as e:
            logger.error(f"Failed to index entity: {e}")
            raise

    def index_relation(self, relation: Dict[str, Any]) -> Dict[str, Any]:
        """
        Index a relationship between entities

        Args:
            relation:
                - from_entity_id: Source entity ID
                - to_entity_id: Target entity ID
                - relation_type: Type (WORKS_AT, KNOWS, etc.)
                - confidence: 0.0-1.0
                - metadata: Optional additional data
        """
        relation["doc_type"] = "relation"
        relation["created_at"] = datetime.utcnow().isoformat()

        # Also update both entities with the relation
        self._add_relation_to_entity(
            relation["from_entity_id"],
            relation["to_entity_id"],
            relation["relation_type"],
            relation.get("confidence", 1.0)
        )

        try:
            response = self.client.index(
                index=self.index_name,
                document=relation,
                refresh=True
            )

            logger.success(f"✓ Created relation: {relation['from_entity_id']} → {relation['to_entity_id']}")

            return {"id": response["_id"], "backend": "elasticsearch"}

        except Exception as e:
            logger.error(f"Failed to index relation: {e}")
            raise

    def index_observation(self, observation: Dict[str, Any]) -> Dict[str, Any]:
        """
        Add observation to an entity

        Args:
            observation:
                - entity_id: Entity to add observation to
                - text: Observation text
                - relevance: 0.0-1.0 score
                - source: Where this came from
        """
        observation["doc_type"] = "observation"
        observation["created_at"] = datetime.utcnow().isoformat()

        # Update parent entity
        self._add_observation_to_entity(
            observation["entity_id"],
            observation["text"],
            observation.get("relevance", 0.5),
            observation.get("source", "unknown")
        )

        try:
            response = self.client.index(
                index=self.index_name,
                document=observation,
                refresh=True
            )

            return {"id": response["_id"], "backend": "elasticsearch"}

        except Exception as e:
            logger.error(f"Failed to index observation: {e}")
            raise

    def _add_relation_to_entity(
        self,
        from_entity_id: str,
        to_entity_id: str,
        relation_type: str,
        confidence: float
    ):
        """Update entity document with new relation"""
        try:
            # Get target entity name
            target_entity = self.client.get(index=self.index_name, id=to_entity_id)
            target_name = target_entity["_source"].get("entity_name", "Unknown")

            # Update source entity
            self.client.update(
                index=self.index_name,
                id=from_entity_id,
                body={
                    "script": {
                        "source": """
                            if (ctx._source.relations == null) {
                                ctx._source.relations = [];
                            }
                            ctx._source.relations.add(params.relation);
                            ctx._source.updated_at = params.timestamp;
                        """,
                        "params": {
                            "relation": {
                                "relation_type": relation_type,
                                "target_entity_id": to_entity_id,
                                "target_entity_name": target_name,
                                "confidence": confidence,
                                "created_at": datetime.utcnow().isoformat()
                            },
                            "timestamp": datetime.utcnow().isoformat()
                        }
                    }
                },
                refresh=True
            )
        except Exception as e:
            logger.warning(f"Could not update entity with relation: {e}")

    def _add_observation_to_entity(
        self,
        entity_id: str,
        text: str,
        relevance: float,
        source: str
    ):
        """Update entity document with new observation"""
        try:
            self.client.update(
                index=self.index_name,
                id=entity_id,
                body={
                    "script": {
                        "source": """
                            if (ctx._source.observations == null) {
                                ctx._source.observations = [];
                            }
                            ctx._source.observations.add(params.observation);
                            ctx._source.updated_at = params.timestamp;
                        """,
                        "params": {
                            "observation": {
                                "text": text,
                                "relevance": relevance,
                                "created_at": datetime.utcnow().isoformat(),
                                "source": source
                            },
                            "timestamp": datetime.utcnow().isoformat()
                        }
                    }
                },
                refresh=True
            )
        except Exception as e:
            logger.warning(f"Could not update entity with observation: {e}")

    # === DOCUMENT OPERATIONS ===

    def index_document(self, document: Dict[str, Any]) -> Dict[str, Any]:
        """
        Index a document with full-text and optional vector embedding

        Args:
            document:
                - title: Document title
                - content: Full text content
                - content_vector: Optional embedding (1536 dims)
                - zone_id: Memory zone
                - file_path: Source file path
                - extracted_entities: Optional list of entity IDs
        """
        document["doc_type"] = "document"
        document["created_at"] = datetime.utcnow().isoformat()
        document["updated_at"] = document["created_at"]
        document["access_count"] = 0

        if "zone_id" not in document:
            document["zone_id"] = config.DEFAULT_ZONE

        try:
            response = self.client.index(
                index=self.index_name,
                document=document,
                refresh=True
            )

            doc_id = response["_id"]
            logger.success(f"✓ Indexed document: {document.get('title', 'Untitled')} ({doc_id})")

            return {"id": doc_id, "backend": "elasticsearch"}

        except Exception as e:
            logger.error(f"Failed to index document: {e}")
            raise

    # === SEARCH OPERATIONS ===

    def search_keyword(
        self,
        query: str,
        zone_id: Optional[str] = None,
        doc_types: Optional[List[str]] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        BM25 keyword search across all content

        Args:
            query: Search query
            zone_id: Optional zone filter
            doc_types: Optional doc type filter (["entity", "document"])
            limit: Max results
        """
        must_clauses = [
            {
                "multi_match": {
                    "query": query,
                    "fields": [
                        "title^3",
                        "content",
                        "entity_name^2",
                        "observations.text"
                    ],
                    "type": "best_fields",
                    "fuzziness": "AUTO"
                }
            }
        ]

        if zone_id:
            must_clauses.append({"term": {"zone_id": zone_id}})

        if doc_types:
            must_clauses.append({"terms": {"doc_type": doc_types}})

        query_body = {
            "query": {"bool": {"must": must_clauses}},
            "size": limit,
            "sort": ["_score", {"updated_at": {"order": "desc"}}]
        }

        try:
            response = self.client.search(
                index=self.index_name,
                body=query_body
            )

            results = [
                {
                    "id": hit["_id"],
                    "score": hit["_score"],
                    **hit["_source"]
                }
                for hit in response["hits"]["hits"]
            ]

            logger.info(f"Found {len(results)} results for: {query}")
            return results

        except Exception as e:
            logger.error(f"Search error: {e}")
            return []

    def search_vector(
        self,
        query_vector: List[float],
        zone_id: Optional[str] = None,
        limit: int = 20,
        min_score: float = 0.7
    ) -> List[Dict[str, Any]]:
        """
        kNN vector similarity search

        Args:
            query_vector: Embedding vector (1536 dims)
            zone_id: Optional zone filter
            limit: Max results
            min_score: Minimum similarity score
        """
        knn_query = {
            "field": "content_vector",
            "query_vector": query_vector,
            "k": limit,
            "num_candidates": limit * 2
        }

        if zone_id:
            knn_query["filter"] = {"term": {"zone_id": zone_id}}

        try:
            response = self.client.search(
                index=self.index_name,
                knn=knn_query,
                size=limit
            )

            results = [
                {
                    "id": hit["_id"],
                    "score": hit["_score"],
                    **hit["_source"]
                }
                for hit in response["hits"]["hits"]
                if hit["_score"] >= min_score
            ]

            logger.info(f"Found {len(results)} vector results")
            return results

        except Exception as e:
            logger.error(f"Vector search error: {e}")
            return []

    def search_hybrid(
        self,
        query_text: str,
        query_vector: List[float],
        zone_id: Optional[str] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Hybrid search: BM25 + kNN combined

        Uses Reciprocal Rank Fusion to merge results
        """
        # Get both result sets
        keyword_results = self.search_keyword(query_text, zone_id, limit=limit)
        vector_results = self.search_vector(query_vector, zone_id, limit=limit)

        # Merge using RRF
        merged = self._reciprocal_rank_fusion(keyword_results, vector_results)

        return merged[:limit]

    def _reciprocal_rank_fusion(
        self,
        results1: List[Dict],
        results2: List[Dict],
        k: int = 60
    ) -> List[Dict]:
        """
        Reciprocal Rank Fusion algorithm to merge ranked lists
        RRF score = 1 / (k + rank)
        """
        scores = {}

        for rank, result in enumerate(results1, 1):
            doc_id = result["id"]
            scores[doc_id] = scores.get(doc_id, 0) + (1.0 / (k + rank))

        for rank, result in enumerate(results2, 1):
            doc_id = result["id"]
            scores[doc_id] = scores.get(doc_id, 0) + (1.0 / (k + rank))

        # Get unique results
        all_results = {r["id"]: r for r in results1 + results2}

        # Sort by RRF score
        sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)

        return [
            {**all_results[doc_id], "rrf_score": scores[doc_id]}
            for doc_id in sorted_ids
            if doc_id in all_results
        ]

    # === GRAPH TRAVERSAL ===

    def traverse_graph(
        self,
        start_entity_id: str,
        max_depth: int = 2,
        relation_filter: Optional[List[str]] = None,
        zone_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Traverse knowledge graph from starting entity

        Args:
            start_entity_id: Entity to start from
            max_depth: How many hops to traverse
            relation_filter: Optional relation types to follow
            zone_id: Optional zone filter
        """
        visited = set()
        results = []

        def _traverse(entity_id: str, depth: int):
            if depth > max_depth or entity_id in visited:
                return

            visited.add(entity_id)

            try:
                # Get entity
                entity = self.client.get(index=self.index_name, id=entity_id)
                entity_data = {"id": entity_id, **entity["_source"]}
                results.append(entity_data)

                # Traverse relations
                relations = entity["_source"].get("relations", [])
                for relation in relations:
                    if relation_filter and relation["relation_type"] not in relation_filter:
                        continue

                    target_id = relation["target_entity_id"]
                    _traverse(target_id, depth + 1)

            except Exception as e:
                logger.warning(f"Could not traverse from {entity_id}: {e}")

        _traverse(start_entity_id, 0)

        logger.info(f"Traversed graph: {len(results)} entities found")
        return results

    # === UTILITY METHODS ===

    def get_by_id(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Get document by ID"""
        try:
            result = self.client.get(index=self.index_name, id=doc_id)
            return {"id": doc_id, **result["_source"]}
        except Exception as e:
            return None

    def delete_by_id(self, doc_id: str) -> bool:
        """Delete document by ID"""
        try:
            self.client.delete(index=self.index_name, id=doc_id, refresh=True)
            return True
        except Exception as e:
            return False

    def count(self, zone_id: Optional[str] = None, doc_type: Optional[str] = None) -> int:
        """Count documents"""
        query = {"query": {"bool": {"must": []}}}

        if zone_id:
            query["query"]["bool"]["must"].append({"term": {"zone_id": zone_id}})
        if doc_type:
            query["query"]["bool"]["must"].append({"term": {"doc_type": doc_type}})

        if not query["query"]["bool"]["must"]:
            query = {"query": {"match_all": {}}}

        result = self.client.count(index=self.index_name, body=query)
        return result["count"]
