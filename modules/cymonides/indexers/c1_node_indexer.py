#!/usr/bin/env python3
"""
Cymonides-1 Node Graph Indexer

Indexes SUBJECT and NEXUS node categories with embeddings for semantic search.

SUBJECT categories (node types):
  - professions (lawyer, doctor, engineer...)
  - titles (CEO, director, founder...)
  - industries (finance, tech, healthcare...)

NEXUS categories (edge types):
  - relationships (officer_of, owns, related_to...)

Each category has:
  - Canonical term
  - Multilingual synonyms
  - Dense vector embeddings (1024-dim, multilingual-e5-large)

Usage:
    from cymonides.indexers.c1_node_indexer import C1NodeIndexer

    indexer = C1NodeIndexer()
    indexer.index_subject_categories()  # Index professions, titles, industries
    indexer.index_nexus_categories()    # Index relationship types

    # Search
    results = indexer.search_semantic("rechtsanwalt", category="professions")
    results = indexer.search_hybrid("финансист", top_k=10)
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass

from elasticsearch import Elasticsearch, helpers

logger = logging.getLogger(__name__)

# Paths
CLASSES_DIR = Path("/data/CLASSES")
SUBJECT_DIR = CLASSES_DIR / "SUBJECT"
NEXUS_DIR = CLASSES_DIR / "NEXUS"

# Index name
INDEX_NAME = "cymonides-1-categories"

# Embedding model
EMBEDDING_MODEL = "intfloat/multilingual-e5-large"
EMBEDDING_DIMS = 1024


@dataclass
class CategoryMatch:
    """Result from category search."""
    canonical: str
    category: str  # professions, titles, industries, relationships
    dimension: str  # SUBJECT or NEXUS
    term: str
    language: str
    score: float


class C1NodeIndexer:
    """
    Indexer for Cymonides-1 node categories.

    Handles SUBJECT (professions/titles/industries) and NEXUS (relationships)
    with multilingual synonyms and dense vector embeddings.
    """

    MAPPING = {
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
            "index": {
                "similarity": {
                    "custom_bm25": {
                        "type": "BM25",
                        "k1": 1.2,
                        "b": 0.75
                    }
                }
            }
        },
        "mappings": {
            "properties": {
                # Identity
                "canonical": {"type": "keyword"},
                "category": {"type": "keyword"},  # professions, titles, industries, relationships
                "dimension": {"type": "keyword"},  # SUBJECT or NEXUS

                # Searchable term
                "term": {
                    "type": "text",
                    "analyzer": "standard",
                    "similarity": "custom_bm25",
                    "fields": {
                        "keyword": {"type": "keyword"},
                        "exact": {"type": "keyword", "normalizer": "lowercase"}
                    }
                },
                "language": {"type": "keyword"},

                # Dense vector for semantic search
                "embedding": {
                    "type": "dense_vector",
                    "dims": EMBEDDING_DIMS,
                    "index": True,
                    "similarity": "cosine"
                },

                # Metadata
                "is_canonical": {"type": "boolean"},
                "weight": {"type": "float"},
                "indexed_at": {"type": "date"}
            }
        }
    }

    def __init__(self, es_host: str = "http://localhost:9200"):
        self.es = Elasticsearch([es_host])
        self._model = None

    @property
    def model(self):
        """Lazy load embedding model."""
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            logger.info(f"Loading embedding model: {EMBEDDING_MODEL}")
            self._model = SentenceTransformer(EMBEDDING_MODEL)
        return self._model

    def create_index(self, force: bool = False) -> bool:
        """Create or recreate the index."""
        if self.es.indices.exists(index=INDEX_NAME):
            if force:
                logger.info(f"Deleting existing index: {INDEX_NAME}")
                self.es.indices.delete(index=INDEX_NAME)
            else:
                logger.info(f"Index {INDEX_NAME} already exists")
                return False

        logger.info(f"Creating index: {INDEX_NAME}")
        self.es.indices.create(index=INDEX_NAME, body=self.MAPPING)
        return True

    def _load_subject_data(self) -> tuple:
        """Load SUBJECT synonyms and embeddings."""
        synonyms_file = SUBJECT_DIR / "synonyms.json"
        embeddings_file = SUBJECT_DIR / "subject_embeddings.json"

        synonyms = {}
        if synonyms_file.exists():
            with open(synonyms_file, "r", encoding="utf-8") as f:
                synonyms = json.load(f)

        embeddings = {}
        if embeddings_file.exists():
            with open(embeddings_file, "r", encoding="utf-8") as f:
                embeddings = json.load(f)

        return synonyms, embeddings

    def _load_nexus_data(self) -> tuple:
        """Load NEXUS relationship synonyms and embeddings."""
        synonyms_file = NEXUS_DIR / "data" / "relationship_synonyms.json"
        embeddings_file = NEXUS_DIR / "data" / "relationship_embeddings.json"

        synonyms = {}
        if synonyms_file.exists():
            with open(synonyms_file, "r", encoding="utf-8") as f:
                synonyms = json.load(f)

        embeddings = {}
        if embeddings_file.exists():
            with open(embeddings_file, "r", encoding="utf-8") as f:
                embeddings = json.load(f)

        return synonyms, embeddings

    def _generate_subject_docs(self, synonyms: Dict, embeddings: Dict):
        """Generate ES documents for SUBJECT categories."""
        now = datetime.now().isoformat()
        emb_data = embeddings.get("embeddings", {})

        for category in ["professions", "titles", "industries"]:
            cat_syns = synonyms.get(category, {})
            cat_embs = emb_data.get(category, {})

            for canonical, langs in cat_syns.items():
                canon_embs = cat_embs.get(canonical, {})

                # Canonical term
                yield {
                    "_index": INDEX_NAME,
                    "_id": f"subject:{category}:{canonical}:canonical",
                    "_source": {
                        "canonical": canonical,
                        "category": category,
                        "dimension": "SUBJECT",
                        "term": canonical,
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
                            "_id": f"subject:{category}:{canonical}:{lang}:{term_lower}",
                            "_source": {
                                "canonical": canonical,
                                "category": category,
                                "dimension": "SUBJECT",
                                "term": term,
                                "language": lang,
                                "embedding": syn_embs.get(term_lower),
                                "is_canonical": False,
                                "weight": 0.8 if lang == "en" else 0.7,
                                "indexed_at": now
                            }
                        }

    def _generate_nexus_docs(self, synonyms: Dict, embeddings: Dict):
        """Generate ES documents for NEXUS relationship categories."""
        now = datetime.now().isoformat()
        emb_data = embeddings.get("embeddings", {})

        rel_syns = synonyms.get("synonyms", {})

        for canonical, langs in rel_syns.items():
            canon_embs = emb_data.get(canonical, {})

            # Canonical term
            yield {
                "_index": INDEX_NAME,
                "_id": f"nexus:relationships:{canonical}:canonical",
                "_source": {
                    "canonical": canonical,
                    "category": "relationships",
                    "dimension": "NEXUS",
                    "term": canonical,
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
                        "_id": f"nexus:relationships:{canonical}:{lang}:{term_lower}",
                        "_source": {
                            "canonical": canonical,
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

    def index_subject_categories(self) -> int:
        """Index all SUBJECT categories (professions, titles, industries)."""
        synonyms, embeddings = self._load_subject_data()

        logger.info("Indexing SUBJECT categories...")
        success, errors = helpers.bulk(
            self.es,
            self._generate_subject_docs(synonyms, embeddings),
            raise_on_error=False
        )

        if errors:
            logger.warning(f"Indexing errors: {len(errors)}")

        self.es.indices.refresh(index=INDEX_NAME)
        logger.info(f"Indexed {success} SUBJECT documents")
        return success

    def index_nexus_categories(self) -> int:
        """Index all NEXUS relationship categories."""
        synonyms, embeddings = self._load_nexus_data()

        logger.info("Indexing NEXUS categories...")
        success, errors = helpers.bulk(
            self.es,
            self._generate_nexus_docs(synonyms, embeddings),
            raise_on_error=False
        )

        if errors:
            logger.warning(f"Indexing errors: {len(errors)}")

        self.es.indices.refresh(index=INDEX_NAME)
        logger.info(f"Indexed {success} NEXUS documents")
        return success

    def index_all(self, force: bool = False) -> Dict[str, int]:
        """Index all categories."""
        self.create_index(force=force)

        return {
            "subject": self.index_subject_categories(),
            "nexus": self.index_nexus_categories()
        }

    # === Search Methods ===

    def search_exact(self, term: str, category: str = None, dimension: str = None) -> List[CategoryMatch]:
        """Exact keyword search."""
        query = {"bool": {"must": [{"term": {"term.exact": term.lower()}}]}}

        if category:
            query["bool"]["filter"] = query["bool"].get("filter", [])
            query["bool"]["filter"].append({"term": {"category": category}})
        if dimension:
            query["bool"]["filter"] = query["bool"].get("filter", [])
            query["bool"]["filter"].append({"term": {"dimension": dimension}})

        result = self.es.search(index=INDEX_NAME, body={"query": query, "size": 10})

        return [
            CategoryMatch(
                canonical=hit["_source"]["canonical"],
                category=hit["_source"]["category"],
                dimension=hit["_source"]["dimension"],
                term=hit["_source"]["term"],
                language=hit["_source"]["language"],
                score=hit["_score"]
            )
            for hit in result["hits"]["hits"]
        ]

    def search_semantic(
        self,
        query: str,
        category: str = None,
        dimension: str = None,
        top_k: int = 10
    ) -> List[CategoryMatch]:
        """Semantic search using embeddings."""
        # Encode query
        query_vec = self.model.encode(f"query: {query}").tolist()

        # Build KNN query
        knn = {
            "field": "embedding",
            "query_vector": query_vec,
            "k": top_k,
            "num_candidates": top_k * 10
        }

        # Add filters
        filters = []
        if category:
            filters.append({"term": {"category": category}})
        if dimension:
            filters.append({"term": {"dimension": dimension}})

        if filters:
            knn["filter"] = {"bool": {"must": filters}}

        result = self.es.search(index=INDEX_NAME, body={"knn": knn, "size": top_k})

        return [
            CategoryMatch(
                canonical=hit["_source"]["canonical"],
                category=hit["_source"]["category"],
                dimension=hit["_source"]["dimension"],
                term=hit["_source"]["term"],
                language=hit["_source"]["language"],
                score=hit["_score"]
            )
            for hit in result["hits"]["hits"]
        ]

    def search_hybrid(
        self,
        query: str,
        category: str = None,
        dimension: str = None,
        top_k: int = 10
    ) -> List[CategoryMatch]:
        """Hybrid search combining BM25 + semantic with RRF."""
        query_vec = self.model.encode(f"query: {query}").tolist()

        # BM25 query
        bm25_query = {
            "bool": {
                "should": [
                    {"match": {"term": query}},
                    {"term": {"term.exact": query.lower()}}
                ]
            }
        }

        # Filters
        filters = []
        if category:
            filters.append({"term": {"category": category}})
        if dimension:
            filters.append({"term": {"dimension": dimension}})

        if filters:
            bm25_query["bool"]["filter"] = filters

        # KNN
        knn = {
            "field": "embedding",
            "query_vector": query_vec,
            "k": top_k,
            "num_candidates": top_k * 10
        }

        if filters:
            knn["filter"] = {"bool": {"must": filters}}

        # RRF fusion
        body = {
            "query": bm25_query,
            "knn": knn,
            "rank": {"rrf": {"window_size": 100, "rank_constant": 60}},
            "size": top_k
        }

        result = self.es.search(index=INDEX_NAME, body=body)

        return [
            CategoryMatch(
                canonical=hit["_source"]["canonical"],
                category=hit["_source"]["category"],
                dimension=hit["_source"]["dimension"],
                term=hit["_source"]["term"],
                language=hit["_source"]["language"],
                score=hit["_score"]
            )
            for hit in result["hits"]["hits"]
        ]

    def resolve_to_canonical(self, term: str, category: str = None) -> Optional[str]:
        """Resolve any synonym to its canonical form."""
        matches = self.search_hybrid(term, category=category, top_k=1)
        return matches[0].canonical if matches else None

    def get_stats(self) -> Dict[str, Any]:
        """Get index statistics."""
        if not self.es.indices.exists(index=INDEX_NAME):
            return {"exists": False}

        count = self.es.count(index=INDEX_NAME)["count"]

        stats = {"exists": True, "total": count, "by_category": {}, "by_dimension": {}}

        for cat in ["professions", "titles", "industries", "relationships"]:
            cat_count = self.es.count(
                index=INDEX_NAME,
                body={"query": {"term": {"category": cat}}}
            )["count"]
            stats["by_category"][cat] = cat_count

        for dim in ["SUBJECT", "NEXUS"]:
            dim_count = self.es.count(
                index=INDEX_NAME,
                body={"query": {"term": {"dimension": dim}}}
            )["count"]
            stats["by_dimension"][dim] = dim_count

        return stats


# CLI
if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    parser = argparse.ArgumentParser(description="Cymonides-1 Node Category Indexer")
    parser.add_argument("--host", default="http://localhost:9200")
    parser.add_argument("--force", action="store_true", help="Recreate index")
    parser.add_argument("--test", action="store_true", help="Run test searches")
    args = parser.parse_args()

    indexer = C1NodeIndexer(es_host=args.host)

    if not indexer.es.ping():
        print(f"Cannot connect to ES at {args.host}")
        exit(1)

    # Index all
    results = indexer.index_all(force=args.force)
    print(f"\nIndexed: SUBJECT={results['subject']}, NEXUS={results['nexus']}")

    # Stats
    stats = indexer.get_stats()
    print(f"\nTotal: {stats['total']}")
    print(f"By category: {stats['by_category']}")
    print(f"By dimension: {stats['by_dimension']}")

    if args.test:
        print("\n=== Test Searches ===")

        print("\n1. Exact: 'rechtsanwalt'")
        for m in indexer.search_exact("rechtsanwalt"):
            print(f"   {m.term} -> {m.canonical} ({m.category})")

        print("\n2. Semantic: 'финансист' (Russian financier)")
        for m in indexer.search_semantic("финансист", top_k=5):
            print(f"   {m.term} -> {m.canonical} ({m.language}) score={m.score:.4f}")

        print("\n3. Hybrid: 'geschäftsführer'")
        for m in indexer.search_hybrid("geschäftsführer", top_k=5):
            print(f"   {m.term} -> {m.canonical} ({m.category})")
