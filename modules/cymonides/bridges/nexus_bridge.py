#!/usr/bin/env python3
"""
NexusBridge - Access NEXUS relationship data from cymonides

Source: /data/CLASSES/NEXUS/
Index: cymonides-1-categories (dimension=NEXUS)

Provides:
  - Relationship synonym lookups
  - Semantic search for relationship types
  - Canonical resolution
  - Pattern generation for relationship extraction
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Source of truth - CLASSES directory
CLASSES_DIR = Path("/data/CLASSES")
NEXUS_DIR = CLASSES_DIR / "NEXUS"

# ES index
INDEX_NAME = "cymonides-1-categories"


@dataclass
class RelationshipMatch:
    """Result from relationship search."""
    canonical: str
    term: str
    language: str
    score: float


class NexusBridge:
    """
    Bridge from cymonides to NEXUS data in CLASSES.

    Loads relationship synonyms and embeddings from CLASSES/NEXUS/.
    Searches via cymonides-1-categories ES index.
    Auto-refreshes index when JSONs change.

    Search methods:
      - exact: Keyword match
      - fuzzy: Edit distance tolerance
      - prefix: Starts with
      - wildcard: Pattern match
      - semantic: Dense vector KNN
      - hybrid: BM25 + semantic with RRF
    """

    def __init__(self, es_host: str = "http://localhost:9200", auto_refresh: bool = True):
        self._synonyms = None
        self._embeddings = None
        self._ontology = None
        self._es = None
        self._es_host = es_host
        self._auto_refresh = auto_refresh
        self._last_json_mtime = None

    # === Lazy Loading ===

    @property
    def synonyms(self) -> Dict:
        if self._synonyms is None:
            self._synonyms = self._load_json(NEXUS_DIR / "data" / "relationship_synonyms.json")
        return self._synonyms

    @property
    def embeddings(self) -> Dict:
        if self._embeddings is None:
            self._embeddings = self._load_json(NEXUS_DIR / "data" / "relationship_embeddings.json")
        return self._embeddings

    @property
    def ontology(self) -> Dict:
        if self._ontology is None:
            self._ontology = self._load_json(NEXUS_DIR / "RELATIONSHIPS" / "ontology.json")
        return self._ontology

    @property
    def es(self):
        if self._es is None:
            from elasticsearch import Elasticsearch
            self._es = Elasticsearch([self._es_host])
        return self._es

    def _load_json(self, path: Path) -> Dict:
        if not path.exists():
            logger.warning(f"File not found: {path}")
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _check_refresh_needed(self) -> bool:
        """Check if JSONs changed and index needs refresh."""
        synonyms_path = NEXUS_DIR / "data" / "relationship_synonyms.json"
        if not synonyms_path.exists():
            return False

        current_mtime = synonyms_path.stat().st_mtime
        if self._last_json_mtime is None:
            self._last_json_mtime = current_mtime
            return False

        if current_mtime > self._last_json_mtime:
            self._last_json_mtime = current_mtime
            return True
        return False

    def refresh_index(self, force: bool = False) -> int:
        """Rebuild ES index from JSONs. Returns doc count."""
        from datetime import datetime
        from elasticsearch import helpers

        if not force and not self._check_refresh_needed():
            logger.info("Index is up to date")
            return 0

        logger.info("Refreshing NEXUS index...")

        # Reload JSONs
        self._synonyms = None
        self._embeddings = None

        def generate_docs():
            now = datetime.now().isoformat()
            emb_data = self.embeddings.get("embeddings", {})
            rel_syns = self.synonyms.get("synonyms", {})

            for rel_type, langs in rel_syns.items():
                canon_embs = emb_data.get(rel_type, {})

                # Canonical
                yield {
                    "_index": INDEX_NAME,
                    "_id": f"nexus:relationships:{rel_type}:canonical",
                    "_source": {
                        "canonical": rel_type,
                        "category": "relationships",
                        "dimension": "NEXUS",
                        "term": rel_type,
                        "language": "canonical",
                        "embedding": canon_embs.get("canonical_embedding"),
                        "is_canonical": True,
                        "weight": 1.0,
                        "indexed_at": now
                    }
                }

                # Synonyms
                for lang, terms in langs.items():
                    if not isinstance(terms, list):
                        continue
                    syn_embs = canon_embs.get("synonyms", {}).get(lang, {})

                    for term in terms:
                        term_lower = term.lower()
                        yield {
                            "_index": INDEX_NAME,
                            "_id": f"nexus:relationships:{rel_type}:{lang}:{term_lower}",
                            "_source": {
                                "canonical": rel_type,
                                "category": "relationships",
                                "dimension": "NEXUS",
                                "term": term,
                                "language": lang,
                                "embedding": syn_embs.get(term_lower),
                                "is_canonical": False,
                                "weight": 0.8 if lang == "en" else 0.7,
                                "indexed_at": now
                            }
                        }

        # Delete existing NEXUS docs
        self.es.delete_by_query(
            index=INDEX_NAME,
            body={"query": {"term": {"dimension": "NEXUS"}}},
            conflicts="proceed"
        )

        # Bulk index
        success, _ = helpers.bulk(self.es, generate_docs(), raise_on_error=False)
        self.es.indices.refresh(index=INDEX_NAME)

        logger.info(f"Refreshed {success} NEXUS documents")
        return success

    # === Synonym Lookups ===

    def get_relationship_synonyms(self, canonical: str, lang: Optional[str] = None) -> List[str]:
        """Get synonyms for a relationship type."""
        rel_data = self.synonyms.get("synonyms", {}).get(canonical, {})
        if lang:
            return rel_data.get(lang, [])
        # All languages
        all_syns = []
        for lang_syns in rel_data.values():
            if isinstance(lang_syns, list):
                all_syns.extend(lang_syns)
        return all_syns

    def get_all_relationship_types(self) -> List[str]:
        """Get all canonical relationship types."""
        return list(self.synonyms.get("synonyms", {}).keys())

    def get_relationship_hierarchy(self) -> Dict:
        """Get relationship ontology hierarchy."""
        return self.ontology.get("hierarchy", {})

    def get_parent_relationship(self, rel_type: str) -> Optional[str]:
        """Get parent relationship in hierarchy (e.g., officer_of -> member_of)."""
        hierarchy = self.get_relationship_hierarchy()
        for parent, children in hierarchy.items():
            if rel_type in children:
                return parent
        return None

    # === ES Search ===

    def search_exact(self, term: str) -> List[RelationshipMatch]:
        """Exact keyword search in ES."""
        query = {
            "bool": {
                "must": [
                    {"term": {"term.keyword": term}},
                    {"term": {"dimension": "NEXUS"}}
                ]
            }
        }

        result = self.es.search(index=INDEX_NAME, body={"query": query, "size": 10})

        return [
            RelationshipMatch(
                canonical=hit["_source"]["canonical"],
                term=hit["_source"]["term"],
                language=hit["_source"]["language"],
                score=hit["_score"]
            )
            for hit in result["hits"]["hits"]
        ]

    def search_semantic(self, query: str, top_k: int = 10) -> List[RelationshipMatch]:
        """Semantic search using ES KNN."""
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer("intfloat/multilingual-e5-large")
        query_vec = model.encode(f"query: {query}").tolist()

        knn = {
            "field": "embedding",
            "query_vector": query_vec,
            "k": top_k,
            "num_candidates": top_k * 10,
            "filter": {"term": {"dimension": "NEXUS"}}
        }

        result = self.es.search(index=INDEX_NAME, body={"knn": knn, "size": top_k})

        return [
            RelationshipMatch(
                canonical=hit["_source"]["canonical"],
                term=hit["_source"]["term"],
                language=hit["_source"]["language"],
                score=hit["_score"]
            )
            for hit in result["hits"]["hits"]
        ]

    def search_hybrid(self, query: str, top_k: int = 10) -> List[RelationshipMatch]:
        """Hybrid BM25 + semantic search with RRF."""
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer("intfloat/multilingual-e5-large")
        query_vec = model.encode(f"query: {query}").tolist()

        # BM25
        bm25_query = {
            "bool": {
                "should": [
                    {"match": {"term": query}},
                    {"term": {"term.keyword": query}}
                ],
                "filter": [{"term": {"dimension": "NEXUS"}}]
            }
        }

        # KNN
        knn = {
            "field": "embedding",
            "query_vector": query_vec,
            "k": top_k,
            "num_candidates": top_k * 10,
            "filter": {"term": {"dimension": "NEXUS"}}
        }

        # RRF
        body = {
            "query": bm25_query,
            "knn": knn,
            "rank": {"rrf": {"window_size": 100, "rank_constant": 60}},
            "size": top_k
        }

        result = self.es.search(index=INDEX_NAME, body=body)

        return [
            RelationshipMatch(
                canonical=hit["_source"]["canonical"],
                term=hit["_source"]["term"],
                language=hit["_source"]["language"],
                score=hit["_score"]
            )
            for hit in result["hits"]["hits"]
        ]

    # === Additional Search Methods ===

    def search_fuzzy(self, term: str, fuzziness: str = "AUTO") -> List[RelationshipMatch]:
        """Fuzzy search with edit distance tolerance."""
        if self._auto_refresh:
            self._check_refresh_needed()

        query = {
            "bool": {
                "must": [
                    {"fuzzy": {"term": {"value": term, "fuzziness": fuzziness}}},
                    {"term": {"dimension": "NEXUS"}}
                ]
            }
        }

        result = self.es.search(index=INDEX_NAME, body={"query": query, "size": 20})

        return [
            RelationshipMatch(
                canonical=hit["_source"]["canonical"],
                term=hit["_source"]["term"],
                language=hit["_source"]["language"],
                score=hit["_score"]
            )
            for hit in result["hits"]["hits"]
        ]

    def search_prefix(self, prefix: str) -> List[RelationshipMatch]:
        """Prefix search - terms starting with prefix."""
        if self._auto_refresh:
            self._check_refresh_needed()

        query = {
            "bool": {
                "must": [
                    {"prefix": {"term": prefix.lower()}},
                    {"term": {"dimension": "NEXUS"}}
                ]
            }
        }

        result = self.es.search(index=INDEX_NAME, body={"query": query, "size": 20})

        return [
            RelationshipMatch(
                canonical=hit["_source"]["canonical"],
                term=hit["_source"]["term"],
                language=hit["_source"]["language"],
                score=hit["_score"]
            )
            for hit in result["hits"]["hits"]
        ]

    def search_wildcard(self, pattern: str) -> List[RelationshipMatch]:
        """Wildcard search - use * and ? in pattern."""
        if self._auto_refresh:
            self._check_refresh_needed()

        query = {
            "bool": {
                "must": [
                    {"wildcard": {"term": pattern.lower()}},
                    {"term": {"dimension": "NEXUS"}}
                ]
            }
        }

        result = self.es.search(index=INDEX_NAME, body={"query": query, "size": 20})

        return [
            RelationshipMatch(
                canonical=hit["_source"]["canonical"],
                term=hit["_source"]["term"],
                language=hit["_source"]["language"],
                score=hit["_score"]
            )
            for hit in result["hits"]["hits"]
        ]

    def search_by_language(self, lang: str) -> List[RelationshipMatch]:
        """Get all relationship terms for a specific language."""
        query = {
            "bool": {
                "must": [
                    {"term": {"language": lang}},
                    {"term": {"dimension": "NEXUS"}}
                ]
            }
        }

        result = self.es.search(index=INDEX_NAME, body={"query": query, "size": 1000})

        return [
            RelationshipMatch(
                canonical=hit["_source"]["canonical"],
                term=hit["_source"]["term"],
                language=hit["_source"]["language"],
                score=hit["_score"]
            )
            for hit in result["hits"]["hits"]
        ]

    def search_all(self, query: str, methods: List[str] = None, top_k: int = 10) -> Dict[str, List[RelationshipMatch]]:
        """
        Run ALL search methods and return combined results.

        Methods: exact, fuzzy, prefix, semantic, hybrid
        """
        if methods is None:
            methods = ["exact", "fuzzy", "prefix", "semantic", "hybrid"]

        results = {}

        if "exact" in methods:
            results["exact"] = self.search_exact(query)

        if "fuzzy" in methods:
            results["fuzzy"] = self.search_fuzzy(query)

        if "prefix" in methods:
            results["prefix"] = self.search_prefix(query)

        if "semantic" in methods:
            results["semantic"] = self.search_semantic(query, top_k)

        if "hybrid" in methods:
            results["hybrid"] = self.search_hybrid(query, top_k)

        return results

    def search_json_direct(self, term: str) -> List[Dict]:
        """
        Search JSONs directly (no ES).
        Useful when ES is down or for offline use.
        """
        term_lower = term.lower()
        results = []

        rel_syns = self.synonyms.get("synonyms", {})

        for canonical, langs in rel_syns.items():
            for lang, terms in langs.items():
                if not isinstance(terms, list):
                    continue
                for t in terms:
                    if term_lower in t.lower() or t.lower() in term_lower:
                        results.append({
                            "canonical": canonical,
                            "term": t,
                            "language": lang,
                            "match_type": "exact" if term_lower == t.lower() else "partial"
                        })

        return results

    # === Resolution ===

    def resolve(self, term: str) -> Optional[str]:
        """Resolve any term to canonical relationship type."""
        # Try exact first
        matches = self.search_exact(term)
        if matches:
            return matches[0].canonical

        # Try fuzzy
        matches = self.search_fuzzy(term)
        if matches:
            return matches[0].canonical

        # Fall back to semantic
        matches = self.search_semantic(term, top_k=1)
        return matches[0].canonical if matches else None

    # === Pattern Generation ===

    def get_extraction_patterns(self) -> List[tuple]:
        """
        Generate regex patterns for relationship extraction.
        Returns [(canonical, pattern), ...]
        """
        import re

        patterns = []
        rel_syns = self.synonyms.get("synonyms", {})

        for canonical, langs in rel_syns.items():
            all_terms = []
            for lang_syns in langs.values():
                if isinstance(lang_syns, list):
                    all_terms.extend(lang_syns)

            if all_terms:
                escaped = [re.escape(t) for t in all_terms if len(t) > 2]
                if escaped:
                    pattern = r'\b(' + '|'.join(escaped) + r')\b'
                    patterns.append((canonical, pattern))

        return patterns

    # === Migration Helpers ===

    def compare_with_edge_types(self, edge_types_path: str) -> Dict[str, Any]:
        """
        Compare NEXUS relationships with existing edge_types.json.
        Returns mapping of what matches, what's new, what's missing.
        """
        with open(edge_types_path, "r") as f:
            edge_types = json.load(f)

        nexus_rels = set(self.get_all_relationship_types())
        edge_rels = set()

        # Extract relationship types from edge_types.json
        for node_type, data in edge_types.items():
            if isinstance(data, dict) and "edge_types" in data:
                for edge in data["edge_types"]:
                    if "relationship_type" in edge:
                        edge_rels.add(edge["relationship_type"])

        return {
            "in_both": list(nexus_rels & edge_rels),
            "only_in_nexus": list(nexus_rels - edge_rels),
            "only_in_edge_types": list(edge_rels - nexus_rels),
            "nexus_count": len(nexus_rels),
            "edge_types_count": len(edge_rels)
        }


# Singleton
_bridge = None

def get_nexus_bridge() -> NexusBridge:
    global _bridge
    if _bridge is None:
        _bridge = NexusBridge()
    return _bridge
