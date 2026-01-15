"""
DRILL Indexer

Elasticsearch indexing with native vector search (dense_vector).
Indexes crawled pages, extracted entities, and embeddings.

Index structure:
- drill_pages: Full page content with metadata
- drill_entities: Extracted entities with embeddings
- drill_links: Outlink graph for link analysis
"""

import os
import asyncio
from typing import List, Dict, Any, Optional, Generator
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json

from elasticsearch import Elasticsearch, helpers
from elasticsearch.exceptions import NotFoundError


@dataclass
class PageDocument:
    """Document representing a crawled page."""
    url: str
    domain: str
    title: str
    content: str
    html_raw: Optional[str] = None
    crawl_timestamp: Optional[str] = None
    status_code: int = 200
    content_type: str = "text/html"
    # Extracted data
    companies: List[str] = None
    persons: List[str] = None
    emails: List[str] = None
    phones: List[str] = None
    outlinks: List[str] = None
    internal_links: List[str] = None
    keywords_found: List[str] = None
    # Embedding
    content_embedding: List[float] = None
    # Metadata
    source: str = "drill"  # Crawl source identifier
    project_id: Optional[str] = None

    def __post_init__(self):
        self.companies = self.companies or []
        self.persons = self.persons or []
        self.emails = self.emails or []
        self.phones = self.phones or []
        self.outlinks = self.outlinks or []
        self.internal_links = self.internal_links or []
        self.keywords_found = self.keywords_found or []
        self.crawl_timestamp = self.crawl_timestamp or datetime.utcnow().isoformat()

    @property
    def doc_id(self) -> str:
        """Generate unique document ID from URL."""
        return hashlib.md5(self.url.encode()).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to Elasticsearch document."""
        doc = {
            "url": self.url,
            "domain": self.domain,
            "title": self.title,
            "content": self.content,
            "crawl_timestamp": self.crawl_timestamp,
            "status_code": self.status_code,
            "content_type": self.content_type,
            "companies": self.companies,
            "persons": self.persons,
            "emails": self.emails,
            "phones": self.phones,
            "outlinks": self.outlinks,
            "internal_links": self.internal_links,
            "keywords_found": self.keywords_found,
            "entity_count": len(self.companies) + len(self.persons) + len(self.emails) + len(self.phones),
            "outlink_count": len(self.outlinks),
            "source": self.source,
        }

        if self.content_embedding:
            doc["content_embedding"] = self.content_embedding

        if self.project_id:
            doc["project_id"] = self.project_id

        if self.html_raw:
            doc["html_raw"] = self.html_raw

        return doc


class DrillIndexer:
    """
    Elasticsearch indexer for DRILL crawler.

    Handles:
    - Index creation with proper mappings (including dense_vector)
    - Bulk document indexing
    - Vector similarity search
    - Entity aggregation queries
    """

    # Index names
    PAGES_INDEX = "drill_pages"
    ENTITIES_INDEX = "drill_entities"
    LINKS_INDEX = "drill_links"

    # Mapping for pages index with vector support
    PAGES_MAPPING = {
        "mappings": {
            "properties": {
                "url": {"type": "keyword"},
                "domain": {"type": "keyword"},
                "title": {"type": "text", "analyzer": "standard"},
                "content": {"type": "text", "analyzer": "standard"},
                "html_raw": {"type": "text", "index": False},  # Store but don't index
                "crawl_timestamp": {"type": "date"},
                "status_code": {"type": "integer"},
                "content_type": {"type": "keyword"},
                # Entity fields
                "companies": {"type": "keyword"},
                "persons": {"type": "keyword"},
                "emails": {"type": "keyword"},
                "phones": {"type": "keyword"},
                "outlinks": {"type": "keyword"},
                "internal_links": {"type": "keyword"},
                "keywords_found": {"type": "keyword"},
                "entity_count": {"type": "integer"},
                "outlink_count": {"type": "integer"},
                # Vector embedding for semantic search
                "content_embedding": {
                    "type": "dense_vector",
                    "dims": 384,  # BGE-small dimensions
                    "index": True,
                    "similarity": "cosine",
                },
                # Metadata
                "source": {"type": "keyword"},
                "project_id": {"type": "keyword"},
            }
        },
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
            "refresh_interval": "5s",
        }
    }

    # Mapping for entities index (denormalized for fast aggregation)
    ENTITIES_MAPPING = {
        "mappings": {
            "properties": {
                "entity_type": {"type": "keyword"},  # company, person, email, phone
                "entity_value": {"type": "keyword"},
                "entity_value_text": {"type": "text"},  # For full-text search
                "source_url": {"type": "keyword"},
                "source_domain": {"type": "keyword"},
                "found_timestamp": {"type": "date"},
                "context": {"type": "text"},  # Surrounding text snippet
                # Vector embedding
                "embedding": {
                    "type": "dense_vector",
                    "dims": 384,
                    "index": True,
                    "similarity": "cosine",
                },
                "project_id": {"type": "keyword"},
            }
        },
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
        }
    }

    # Mapping for links index (for graph analysis)
    LINKS_MAPPING = {
        "mappings": {
            "properties": {
                "source_url": {"type": "keyword"},
                "source_domain": {"type": "keyword"},
                "target_url": {"type": "keyword"},
                "target_domain": {"type": "keyword"},
                "anchor_text": {"type": "text"},
                "link_type": {"type": "keyword"},  # outlink, internal
                "found_timestamp": {"type": "date"},
                "project_id": {"type": "keyword"},
            }
        },
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
        }
    }

    def __init__(
        self,
        elasticsearch_url: Optional[str] = None,
        index_prefix: str = "",
    ):
        """
        Initialize indexer.

        Args:
            elasticsearch_url: ES URL (defaults to env var or localhost)
            index_prefix: Optional prefix for index names (e.g., "project1_")
        """
        self.es_url = elasticsearch_url or os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")
        self.es = Elasticsearch([self.es_url])
        self.index_prefix = index_prefix

        # Prefixed index names
        self.pages_index = f"{index_prefix}{self.PAGES_INDEX}" if index_prefix else self.PAGES_INDEX
        self.entities_index = f"{index_prefix}{self.ENTITIES_INDEX}" if index_prefix else self.ENTITIES_INDEX
        self.links_index = f"{index_prefix}{self.LINKS_INDEX}" if index_prefix else self.LINKS_INDEX

    def ensure_indices(self):
        """Create indices if they don't exist."""
        indices_config = [
            (self.pages_index, self.PAGES_MAPPING),
            (self.entities_index, self.ENTITIES_MAPPING),
            (self.links_index, self.LINKS_MAPPING),
        ]

        for index_name, mapping in indices_config:
            if not self.es.indices.exists(index=index_name):
                self.es.indices.create(index=index_name, body=mapping)
                print(f"Created index: {index_name}")

    def index_page(self, page: PageDocument) -> str:
        """
        Index a single crawled page.

        Args:
            page: PageDocument to index

        Returns:
            Document ID
        """
        self.es.index(
            index=self.pages_index,
            id=page.doc_id,
            document=page.to_dict(),
        )
        return page.doc_id

    def index_pages_bulk(
        self,
        pages: List[PageDocument],
        chunk_size: int = 500,
    ) -> Dict[str, int]:
        """
        Bulk index multiple pages.

        Args:
            pages: List of PageDocuments
            chunk_size: Bulk operation chunk size

        Returns:
            Dict with success/error counts
        """
        def generate_actions() -> Generator[Dict, None, None]:
            for page in pages:
                yield {
                    "_index": self.pages_index,
                    "_id": page.doc_id,
                    "_source": page.to_dict(),
                }

        success, errors = helpers.bulk(
            self.es,
            generate_actions(),
            chunk_size=chunk_size,
            raise_on_error=False,
        )

        return {"success": success, "errors": len(errors) if errors else 0}

    def index_entity(
        self,
        entity_type: str,
        entity_value: str,
        source_url: str,
        source_domain: str,
        embedding: Optional[List[float]] = None,
        context: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> str:
        """Index a single extracted entity."""
        doc_id = hashlib.md5(f"{entity_type}:{entity_value}:{source_url}".encode()).hexdigest()

        doc = {
            "entity_type": entity_type,
            "entity_value": entity_value,
            "entity_value_text": entity_value,
            "source_url": source_url,
            "source_domain": source_domain,
            "found_timestamp": datetime.utcnow().isoformat(),
            "context": context,
        }

        if embedding:
            doc["embedding"] = embedding

        if project_id:
            doc["project_id"] = project_id

        self.es.index(index=self.entities_index, id=doc_id, document=doc)
        return doc_id

    def index_link(
        self,
        source_url: str,
        source_domain: str,
        target_url: str,
        target_domain: str,
        anchor_text: Optional[str] = None,
        link_type: str = "outlink",
        project_id: Optional[str] = None,
    ) -> str:
        """Index a link relationship."""
        doc_id = hashlib.md5(f"{source_url}:{target_url}".encode()).hexdigest()

        doc = {
            "source_url": source_url,
            "source_domain": source_domain,
            "target_url": target_url,
            "target_domain": target_domain,
            "anchor_text": anchor_text,
            "link_type": link_type,
            "found_timestamp": datetime.utcnow().isoformat(),
        }

        if project_id:
            doc["project_id"] = project_id

        self.es.index(index=self.links_index, id=doc_id, document=doc)
        return doc_id

    def bulk_index_entities(
        self,
        entities: List[Dict[str, Any]],
        chunk_size: int = 500,
    ) -> Dict[str, int]:
        """
        Bulk index multiple entities efficiently.

        Args:
            entities: List of entity dicts with keys:
                - entity_type, entity_value, source_url, source_domain
                - Optional: embedding, context, project_id
            chunk_size: Number of docs to index per batch

        Returns:
            Dict with success/error counts
        """
        def generate_actions():
            for entity in entities:
                doc_id = hashlib.md5(
                    f"{entity['entity_type']}:{entity['entity_value']}:{entity['source_url']}".encode()
                ).hexdigest()

                doc = {
                    "entity_type": entity["entity_type"],
                    "entity_value": entity["entity_value"],
                    "entity_value_text": entity["entity_value"],
                    "source_url": entity["source_url"],
                    "source_domain": entity["source_domain"],
                    "found_timestamp": datetime.utcnow().isoformat(),
                }

                if entity.get("context"):
                    doc["context"] = entity["context"]
                if entity.get("embedding"):
                    doc["embedding"] = entity["embedding"]
                if entity.get("project_id"):
                    doc["project_id"] = entity["project_id"]

                yield {
                    "_index": self.entities_index,
                    "_id": doc_id,
                    "_source": doc,
                }

        success, errors = helpers.bulk(
            self.es,
            generate_actions(),
            chunk_size=chunk_size,
            raise_on_error=False,
        )

        return {"success": success, "errors": len(errors) if errors else 0}

    def index_entities_from_extraction(
        self,
        source_url: str,
        source_domain: str,
        companies: List[str] = None,
        persons: List[str] = None,
        emails: List[str] = None,
        phones: List[str] = None,
        project_id: Optional[str] = None,
    ) -> Dict[str, int]:
        """
        Index all entities from an extraction result.

        Convenience method that takes extracted entity lists and bulk indexes them.
        This is the primary method for storing DRILL-extracted entities.

        Args:
            source_url: URL where entities were found
            source_domain: Domain of the source URL
            companies: List of company names
            persons: List of person names
            emails: List of email addresses
            phones: List of phone numbers
            project_id: Optional project identifier

        Returns:
            Dict with counts by entity type and totals
        """
        entities = []

        for company in (companies or []):
            entities.append({
                "entity_type": "company",
                "entity_value": company,
                "source_url": source_url,
                "source_domain": source_domain,
                "project_id": project_id,
            })

        for person in (persons or []):
            entities.append({
                "entity_type": "person",
                "entity_value": person,
                "source_url": source_url,
                "source_domain": source_domain,
                "project_id": project_id,
            })

        for email in (emails or []):
            entities.append({
                "entity_type": "email",
                "entity_value": email,
                "source_url": source_url,
                "source_domain": source_domain,
                "project_id": project_id,
            })

        for phone in (phones or []):
            entities.append({
                "entity_type": "phone",
                "entity_value": phone,
                "source_url": source_url,
                "source_domain": source_domain,
                "project_id": project_id,
            })

        if not entities:
            return {
                "companies": 0, "persons": 0, "emails": 0, "phones": 0,
                "total": 0, "success": 0, "errors": 0
            }

        result = self.bulk_index_entities(entities)

        return {
            "companies": len(companies or []),
            "persons": len(persons or []),
            "emails": len(emails or []),
            "phones": len(phones or []),
            "total": len(entities),
            **result
        }

    # ========================================================================
    # QUERY METHODS
    # ========================================================================

    def search_pages(
        self,
        query: str,
        domain: Optional[str] = None,
        size: int = 20,
    ) -> List[Dict[str, Any]]:
        """Full-text search on pages."""
        must = [{"multi_match": {"query": query, "fields": ["title^2", "content"]}}]

        if domain:
            must.append({"term": {"domain": domain}})

        body = {
            "query": {"bool": {"must": must}},
            "size": size,
            "_source": {"excludes": ["html_raw", "content_embedding"]},
        }

        result = self.es.search(index=self.pages_index, body=body)
        return [hit["_source"] for hit in result["hits"]["hits"]]

    def search_similar(
        self,
        embedding: List[float],
        k: int = 10,
        min_score: float = 0.7,
        domain: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Vector similarity search using kNN.

        Args:
            embedding: Query embedding vector
            k: Number of results
            min_score: Minimum similarity score
            domain: Optional domain filter

        Returns:
            List of similar documents with scores
        """
        query = {
            "knn": {
                "field": "content_embedding",
                "query_vector": embedding,
                "k": k,
                "num_candidates": k * 10,
            }
        }

        if domain:
            query["knn"]["filter"] = {"term": {"domain": domain}}

        result = self.es.search(
            index=self.pages_index,
            body=query,
            _source={"excludes": ["html_raw", "content_embedding"]},
        )

        return [
            {**hit["_source"], "score": hit["_score"]}
            for hit in result["hits"]["hits"]
            if hit["_score"] >= min_score
        ]

    def search_entities(
        self,
        entity_type: Optional[str] = None,
        query: Optional[str] = None,
        domain: Optional[str] = None,
        size: int = 100,
    ) -> List[Dict[str, Any]]:
        """Search extracted entities."""
        must = []

        if entity_type:
            must.append({"term": {"entity_type": entity_type}})

        if query:
            must.append({"match": {"entity_value_text": query}})

        if domain:
            must.append({"term": {"source_domain": domain}})

        body = {
            "query": {"bool": {"must": must}} if must else {"match_all": {}},
            "size": size,
        }

        result = self.es.search(index=self.entities_index, body=body)
        return [hit["_source"] for hit in result["hits"]["hits"]]

    def get_entity_aggregations(
        self,
        domain: Optional[str] = None,
        entity_types: Optional[List[str]] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get aggregated entity counts by type.

        Returns:
            Dict with entity type as key, list of {value, count} as value
        """
        aggs = {
            "by_type": {
                "terms": {"field": "entity_type", "size": 10},
                "aggs": {
                    "top_values": {
                        "terms": {"field": "entity_value", "size": 50}
                    }
                }
            }
        }

        filters = []
        if domain:
            filters.append({"term": {"source_domain": domain}})
        if entity_types:
            filters.append({"terms": {"entity_type": entity_types}})

        body = {
            "size": 0,
            "aggs": aggs,
        }

        if filters:
            body["query"] = {"bool": {"filter": filters}}

        result = self.es.search(index=self.entities_index, body=body)

        aggregations = {}
        for type_bucket in result["aggregations"]["by_type"]["buckets"]:
            entity_type = type_bucket["key"]
            values = [
                {"value": v["key"], "count": v["doc_count"]}
                for v in type_bucket["top_values"]["buckets"]
            ]
            aggregations[entity_type] = values

        return aggregations

    def get_outlinks_for_domain(
        self,
        domain: str,
        size: int = 1000,
    ) -> List[Dict[str, Any]]:
        """Get all outlinks from a domain."""
        body = {
            "query": {"term": {"source_domain": domain}},
            "size": size,
        }

        result = self.es.search(index=self.links_index, body=body)
        return [hit["_source"] for hit in result["hits"]["hits"]]

    def get_backlinks_to_domain(
        self,
        domain: str,
        size: int = 1000,
    ) -> List[Dict[str, Any]]:
        """Get all backlinks pointing to a domain."""
        body = {
            "query": {"term": {"target_domain": domain}},
            "size": size,
        }

        result = self.es.search(index=self.links_index, body=body)
        return [hit["_source"] for hit in result["hits"]["hits"]]

    def get_page_count(self, domain: Optional[str] = None) -> int:
        """Get total page count, optionally filtered by domain."""
        body = {"query": {"term": {"domain": domain}}} if domain else {"query": {"match_all": {}}}
        result = self.es.count(index=self.pages_index, body=body)
        return result["count"]

    def delete_by_domain(self, domain: str) -> Dict[str, int]:
        """Delete all data for a domain."""
        results = {}

        for index in [self.pages_index, self.entities_index, self.links_index]:
            try:
                result = self.es.delete_by_query(
                    index=index,
                    body={"query": {"term": {"domain": domain}}},
                )
                results[index] = result.get("deleted", 0)
            except NotFoundError:
                results[index] = 0

        return results


# Singleton instance
_default_indexer: Optional[DrillIndexer] = None


def get_indexer() -> DrillIndexer:
    """Get default indexer instance."""
    global _default_indexer
    if _default_indexer is None:
        _default_indexer = DrillIndexer()
        _default_indexer.ensure_indices()
    return _default_indexer
