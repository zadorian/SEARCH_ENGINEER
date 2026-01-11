"""
CyMonides 2.0 - Whoosh Backend (Backup)
Lightweight search backend using Whoosh for emergency/portable cases
"""

from typing import Dict, List, Any, Optional
from pathlib import Path
from datetime import datetime
import json
from whoosh import index
from whoosh.fields import Schema, TEXT, KEYWORD, ID, DATETIME, NUMERIC
from whoosh.qparser import QueryParser, MultifieldParser
from whoosh.query import And, Term
from config.unified_config import config


class WhooshBackend:
    """
    Whoosh Backend Implementation

    Lightweight backup backend for when Elasticsearch is unavailable.
    Provides same interface as ElasticsearchBackend but with simpler implementation.

    Limitations compared to Elasticsearch:
    - No native vector search (falls back to keyword)
    - No hybrid search (BM25 only)
    - Simpler relation traversal
    - Lower performance at scale
    """

    def __init__(self):
        """Initialize Whoosh backend"""
        self.index_dir = Path(config.WHOOSH_INDEX_DIR)
        self.index_dir.mkdir(parents=True, exist_ok=True)

        # Schema definition
        self.schema = Schema(
            id=ID(stored=True, unique=True),
            doc_type=KEYWORD(stored=True),
            entity_type=KEYWORD(stored=True),
            entity_name=TEXT(stored=True),
            zone_id=KEYWORD(stored=True),
            content=TEXT(stored=True),
            title=TEXT(stored=True),
            tags=KEYWORD(stored=True, commas=True),
            country=KEYWORD(stored=True),
            created_at=DATETIME(stored=True),
            # Store full JSON for retrieval
            source_json=TEXT(stored=True)
        )

        # Create or open index
        if index.exists_in(str(self.index_dir)):
            self.ix = index.open_dir(str(self.index_dir))
            print(f"✅ Opened existing Whoosh index at {self.index_dir}")
        else:
            self.ix = index.create_in(str(self.index_dir), self.schema)
            print(f"✅ Created new Whoosh index at {self.index_dir}")

    # === Entity Operations ===

    def index_entity(self, entity: Dict[str, Any]) -> Dict[str, Any]:
        """Index an entity"""
        entity["doc_type"] = "entity"
        entity["created_at"] = entity.get("created_at", datetime.utcnow().isoformat())

        # Generate ID if not present
        if "id" not in entity:
            entity["id"] = self._generate_id()

        writer = self.ix.writer()
        try:
            # Extract fields
            doc_id = entity["id"]
            doc = {
                "id": str(doc_id),
                "doc_type": entity["doc_type"],
                "entity_type": entity.get("entity_type", ""),
                "entity_name": entity.get("name", ""),
                "zone_id": entity.get("zone_id", "default"),
                "content": self._extract_searchable_content(entity),
                "tags": ",".join(entity.get("tags", [])),
                "country": entity.get("country", ""),
                "created_at": datetime.fromisoformat(entity["created_at"].replace("Z", "+00:00")),
                "source_json": json.dumps(entity)
            }

            writer.update_document(**doc)
            writer.commit()

            return {"id": doc_id, "backend": "whoosh"}

        except Exception as e:
            writer.cancel()
            raise Exception(f"Failed to index entity: {e}")

    def index_relation(self, relation: Dict[str, Any]) -> Dict[str, Any]:
        """Index a relation"""
        relation["doc_type"] = "relation"
        relation["created_at"] = relation.get("created_at", datetime.utcnow().isoformat())

        if "id" not in relation:
            relation["id"] = self._generate_id()

        writer = self.ix.writer()
        try:
            doc_id = relation["id"]
            doc = {
                "id": str(doc_id),
                "doc_type": "relation",
                "zone_id": relation.get("zone_id", "default"),
                "content": f"{relation.get('from_entity', '')} {relation.get('relation_type', '')} {relation.get('to_entity', '')}",
                "created_at": datetime.fromisoformat(relation["created_at"].replace("Z", "+00:00")),
                "source_json": json.dumps(relation)
            }

            writer.update_document(**doc)
            writer.commit()

            return {"id": doc_id, "backend": "whoosh"}

        except Exception as e:
            writer.cancel()
            raise Exception(f"Failed to index relation: {e}")

    def index_observation(self, observation: Dict[str, Any]) -> Dict[str, Any]:
        """Index an observation"""
        observation["doc_type"] = "observation"
        observation["created_at"] = observation.get("created_at", datetime.utcnow().isoformat())

        if "id" not in observation:
            observation["id"] = self._generate_id()

        writer = self.ix.writer()
        try:
            doc_id = observation["id"]
            doc = {
                "id": str(doc_id),
                "doc_type": "observation",
                "zone_id": observation.get("zone_id", "default"),
                "content": observation.get("text", ""),
                "created_at": datetime.fromisoformat(observation["created_at"].replace("Z", "+00:00")),
                "source_json": json.dumps(observation)
            }

            writer.update_document(**doc)
            writer.commit()

            return {"id": doc_id, "backend": "whoosh"}

        except Exception as e:
            writer.cancel()
            raise Exception(f"Failed to index observation: {e}")

    # === Document Operations ===

    def index_document(self, document: Dict[str, Any]) -> Dict[str, Any]:
        """Index a document"""
        document["doc_type"] = "document"
        document["created_at"] = document.get("created_at", datetime.utcnow().isoformat())

        if "id" not in document:
            document["id"] = self._generate_id()

        writer = self.ix.writer()
        try:
            doc_id = document["id"]
            doc = {
                "id": str(doc_id),
                "doc_type": "document",
                "title": document.get("title", ""),
                "zone_id": document.get("zone_id", "default"),
                "content": document.get("content", ""),
                "tags": ",".join(document.get("tags", [])),
                "created_at": datetime.fromisoformat(document["created_at"].replace("Z", "+00:00")),
                "source_json": json.dumps(document)
            }

            writer.update_document(**doc)
            writer.commit()

            return {"id": doc_id, "backend": "whoosh"}

        except Exception as e:
            writer.cancel()
            raise Exception(f"Failed to index document: {e}")

    # === Search Operations ===

    def search_keyword(
        self,
        query: str,
        zone_id: Optional[str] = None,
        doc_type: Optional[str] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """BM25 keyword search"""
        with self.ix.searcher() as searcher:
            # Build query
            parser = MultifieldParser(["content", "entity_name", "title"], schema=self.schema)
            query_obj = parser.parse(query)

            # Add filters
            filters = []
            if zone_id:
                filters.append(Term("zone_id", zone_id))
            if doc_type:
                filters.append(Term("doc_type", doc_type))

            if filters:
                query_obj = And([query_obj] + filters)

            # Execute search
            results = searcher.search(query_obj, limit=limit)

            # Convert to list
            hits = []
            for hit in results:
                source = json.loads(hit["source_json"])
                source["_id"] = hit["id"]
                source["_score"] = hit.score
                hits.append(source)

            return hits

    def search_vector(
        self,
        query_vector: List[float],
        zone_id: Optional[str] = None,
        doc_type: Optional[str] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Vector search not supported in Whoosh
        Returns empty list
        """
        print("⚠️  Vector search not supported in Whoosh backend")
        return []

    def search_hybrid(
        self,
        query_text: str,
        query_vector: List[float],
        zone_id: Optional[str] = None,
        doc_type: Optional[str] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Hybrid search not supported - falls back to keyword only
        """
        print("⚠️  Hybrid search not supported in Whoosh, using keyword search only")
        return self.search_keyword(query_text, zone_id, doc_type, limit)

    # === Graph Operations ===

    def traverse_graph(
        self,
        start_entity_id: str,
        max_depth: int = 2,
        relation_filter: Optional[List[str]] = None,
        zone_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Traverse knowledge graph (simplified version)
        """
        visited = set()
        result = {
            "start_entity": start_entity_id,
            "entities": [],
            "relations": []
        }

        # Get starting entity
        start_entity = self.get_by_id(start_entity_id)
        if not start_entity:
            return result

        result["entities"].append(start_entity)
        visited.add(start_entity_id)

        # Recursively find connected entities
        self._traverse_recursive(
            start_entity_id,
            visited,
            result,
            max_depth,
            relation_filter,
            zone_id,
            current_depth=0
        )

        return result

    def _traverse_recursive(
        self,
        entity_id: str,
        visited: set,
        result: Dict[str, Any],
        max_depth: int,
        relation_filter: Optional[List[str]],
        zone_id: Optional[str],
        current_depth: int
    ):
        """Recursive graph traversal helper"""
        if current_depth >= max_depth:
            return

        # Find relations involving this entity
        with self.ix.searcher() as searcher:
            # Search for relations
            query = Term("doc_type", "relation")
            results = searcher.search(query, limit=1000)

            for hit in results:
                relation = json.loads(hit["source_json"])

                # Filter by zone
                if zone_id and relation.get("zone_id") != zone_id:
                    continue

                # Filter by relation type
                if relation_filter and relation.get("relation_type") not in relation_filter:
                    continue

                from_id = relation.get("from_entity")
                to_id = relation.get("to_entity")

                # Check if this relation involves our entity
                if from_id == entity_id or to_id == entity_id:
                    result["relations"].append(relation)

                    # Find the other entity
                    other_id = to_id if from_id == entity_id else from_id

                    if other_id not in visited:
                        visited.add(other_id)
                        other_entity = self.get_by_id(other_id)
                        if other_entity:
                            result["entities"].append(other_entity)
                            # Recurse
                            self._traverse_recursive(
                                other_id,
                                visited,
                                result,
                                max_depth,
                                relation_filter,
                                zone_id,
                                current_depth + 1
                            )

    # === Utility Operations ===

    def get_by_id(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Get document by ID"""
        with self.ix.searcher() as searcher:
            query = Term("id", str(doc_id))
            results = searcher.search(query, limit=1)

            if len(results) > 0:
                hit = results[0]
                source = json.loads(hit["source_json"])
                source["_id"] = hit["id"]
                return source

        return None

    def delete_by_id(self, doc_id: str) -> bool:
        """Delete document by ID"""
        writer = self.ix.writer()
        try:
            writer.delete_by_term("id", str(doc_id))
            writer.commit()
            return True
        except Exception as e:
            writer.cancel()
            raise Exception(f"Failed to delete document: {e}")

    def count(self, zone_id: Optional[str] = None, doc_type: Optional[str] = None) -> int:
        """Count documents"""
        with self.ix.searcher() as searcher:
            # Build query
            filters = []
            if zone_id:
                filters.append(Term("zone_id", zone_id))
            if doc_type:
                filters.append(Term("doc_type", doc_type))

            if filters:
                query = And(filters)
                results = searcher.search(query, limit=None)
                return len(results)
            else:
                return searcher.doc_count_all()

    # === Helper Methods ===

    def _generate_id(self) -> str:
        """Generate unique document ID"""
        import uuid
        return str(uuid.uuid4())

    def _extract_searchable_content(self, entity: Dict[str, Any]) -> str:
        """Extract searchable text from entity"""
        parts = []

        # Add name
        if name := entity.get("name"):
            parts.append(name)

        # Add description
        if desc := entity.get("description"):
            parts.append(desc)

        # Add observations
        if observations := entity.get("observations"):
            for obs in observations:
                if isinstance(obs, dict) and "text" in obs:
                    parts.append(obs["text"])
                elif isinstance(obs, str):
                    parts.append(obs)

        # Add other string fields
        for key, value in entity.items():
            if key not in ["name", "description", "observations", "relations", "id", "created_at"]:
                if isinstance(value, str):
                    parts.append(value)

        return " ".join(parts)

    def optimize(self):
        """Optimize the Whoosh index"""
        try:
            self.ix.optimize()
            print("✅ Whoosh index optimized")
        except Exception as e:
            print(f"⚠️  Index optimization failed: {e}")

    def __repr__(self):
        """String representation"""
        doc_count = self.count()
        return f"WhooshBackend(index_dir={self.index_dir}, documents={doc_count})"
