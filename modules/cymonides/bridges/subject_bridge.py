#!/usr/bin/env python3
"""
SubjectBridge - Access SUBJECT data from cymonides

Source: /data/CLASSES/SUBJECT/
Index: cymonides-1-categories (dimension=SUBJECT)

Provides:
  - Synonym lookups (professions, titles, industries)
  - Semantic search via ES dense_vector
  - Canonical resolution
  - Pattern generation for extraction
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Source of truth - CLASSES directory
CLASSES_DIR = Path("/data/CLASSES")
SUBJECT_DIR = CLASSES_DIR / "SUBJECT"

# ES index
INDEX_NAME = "cymonides-1-categories"


@dataclass
class CategoryMatch:
    """Result from category search."""
    canonical: str
    category: str
    term: str
    language: str
    score: float


class SubjectBridge:
    """
    Bridge from cymonides to SUBJECT data in CLASSES.

    Loads synonyms and embeddings from CLASSES/SUBJECT/.
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
        self._es = None
        self._es_host = es_host
        self._auto_refresh = auto_refresh
        self._last_json_mtime = None

    # === Lazy Loading ===

    @property
    def synonyms(self) -> Dict:
        if self._synonyms is None:
            self._synonyms = self._load_json(SUBJECT_DIR / "synonyms.json")
        return self._synonyms

    @property
    def embeddings(self) -> Dict:
        if self._embeddings is None:
            self._embeddings = self._load_json(SUBJECT_DIR / "subject_embeddings.json")
        return self._embeddings

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
        synonyms_path = SUBJECT_DIR / "synonyms.json"
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

        logger.info("Refreshing SUBJECT index...")

        # Reload JSONs
        self._synonyms = None
        self._embeddings = None

        def generate_docs():
            now = datetime.now().isoformat()
            emb_data = self.embeddings.get("embeddings", {})

            for category in ["professions", "titles", "industries"]:
                cat_syns = self.synonyms.get(category, {})
                cat_embs = emb_data.get(category, {})

                for canonical, langs in cat_syns.items():
                    canon_embs = cat_embs.get(canonical, {})

                    # Canonical
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

        # Delete existing SUBJECT docs
        self.es.delete_by_query(
            index=INDEX_NAME,
            body={"query": {"term": {"dimension": "SUBJECT"}}},
            conflicts="proceed"
        )

        # Bulk index
        success, _ = helpers.bulk(self.es, generate_docs(), raise_on_error=False)
        self.es.indices.refresh(index=INDEX_NAME)

        logger.info(f"Refreshed {success} SUBJECT documents")
        return success

    # === Synonym Lookups ===

    def get_profession_synonyms(self, canonical: str, lang: Optional[str] = None) -> List[str]:
        """Get synonyms for a profession."""
        return self._get_synonyms("professions", canonical, lang)

    def get_title_synonyms(self, canonical: str, lang: Optional[str] = None) -> List[str]:
        """Get synonyms for a title."""
        return self._get_synonyms("titles", canonical, lang)

    def get_industry_synonyms(self, canonical: str, lang: Optional[str] = None) -> List[str]:
        """Get synonyms for an industry."""
        return self._get_synonyms("industries", canonical, lang)

    def _get_synonyms(self, category: str, canonical: str, lang: Optional[str] = None) -> List[str]:
        cat_data = self.synonyms.get(category, {}).get(canonical, {})
        if lang:
            return cat_data.get(lang, [])
        # All languages
        all_syns = []
        for lang_syns in cat_data.values():
            if isinstance(lang_syns, list):
                all_syns.extend(lang_syns)
        return all_syns

    def get_all_canonicals(self, category: str) -> List[str]:
        """Get all canonical terms for a category."""
        return list(self.synonyms.get(category, {}).keys())

    # === ES Search ===

    def search_exact(self, term: str, category: str = None) -> List[CategoryMatch]:
        """Exact keyword search in ES."""
        query = {
            "bool": {
                "must": [
                    {"term": {"term.keyword": term}},
                    {"term": {"dimension": "SUBJECT"}}
                ]
            }
        }
        if category:
            query["bool"]["must"].append({"term": {"category": category}})

        result = self.es.search(index=INDEX_NAME, body={"query": query, "size": 10})

        return [
            CategoryMatch(
                canonical=hit["_source"]["canonical"],
                category=hit["_source"]["category"],
                term=hit["_source"]["term"],
                language=hit["_source"]["language"],
                score=hit["_score"]
            )
            for hit in result["hits"]["hits"]
        ]

    def search_semantic(self, query: str, category: str = None, top_k: int = 10) -> List[CategoryMatch]:
        """Semantic search using ES KNN."""
        from sentence_transformers import SentenceTransformer

        # Load model
        model = SentenceTransformer("intfloat/multilingual-e5-large")
        query_vec = model.encode(f"query: {query}").tolist()

        # KNN search
        knn = {
            "field": "embedding",
            "query_vector": query_vec,
            "k": top_k,
            "num_candidates": top_k * 10
        }

        filters = [{"term": {"dimension": "SUBJECT"}}]
        if category:
            filters.append({"term": {"category": category}})

        knn["filter"] = {"bool": {"must": filters}}

        result = self.es.search(index=INDEX_NAME, body={"knn": knn, "size": top_k})

        return [
            CategoryMatch(
                canonical=hit["_source"]["canonical"],
                category=hit["_source"]["category"],
                term=hit["_source"]["term"],
                language=hit["_source"]["language"],
                score=hit["_score"]
            )
            for hit in result["hits"]["hits"]
        ]

    def search_hybrid(self, query: str, category: str = None, top_k: int = 10) -> List[CategoryMatch]:
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
                "filter": [{"term": {"dimension": "SUBJECT"}}]
            }
        }
        if category:
            bm25_query["bool"]["filter"].append({"term": {"category": category}})

        # KNN
        knn = {
            "field": "embedding",
            "query_vector": query_vec,
            "k": top_k,
            "num_candidates": top_k * 10
        }
        knn_filters = [{"term": {"dimension": "SUBJECT"}}]
        if category:
            knn_filters.append({"term": {"category": category}})
        knn["filter"] = {"bool": {"must": knn_filters}}

        # RRF
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
                term=hit["_source"]["term"],
                language=hit["_source"]["language"],
                score=hit["_score"]
            )
            for hit in result["hits"]["hits"]
        ]

    # === Additional Search Methods ===

    def search_fuzzy(self, term: str, category: str = None, fuzziness: str = "AUTO") -> List[CategoryMatch]:
        """Fuzzy search with edit distance tolerance."""
        if self._auto_refresh:
            self._check_refresh_needed()

        query = {
            "bool": {
                "must": [
                    {"fuzzy": {"term": {"value": term, "fuzziness": fuzziness}}},
                    {"term": {"dimension": "SUBJECT"}}
                ]
            }
        }
        if category:
            query["bool"]["must"].append({"term": {"category": category}})

        result = self.es.search(index=INDEX_NAME, body={"query": query, "size": 20})

        return [
            CategoryMatch(
                canonical=hit["_source"]["canonical"],
                category=hit["_source"]["category"],
                term=hit["_source"]["term"],
                language=hit["_source"]["language"],
                score=hit["_score"]
            )
            for hit in result["hits"]["hits"]
        ]

    def search_prefix(self, prefix: str, category: str = None) -> List[CategoryMatch]:
        """Prefix search - terms starting with prefix."""
        if self._auto_refresh:
            self._check_refresh_needed()

        query = {
            "bool": {
                "must": [
                    {"prefix": {"term": prefix.lower()}},
                    {"term": {"dimension": "SUBJECT"}}
                ]
            }
        }
        if category:
            query["bool"]["must"].append({"term": {"category": category}})

        result = self.es.search(index=INDEX_NAME, body={"query": query, "size": 20})

        return [
            CategoryMatch(
                canonical=hit["_source"]["canonical"],
                category=hit["_source"]["category"],
                term=hit["_source"]["term"],
                language=hit["_source"]["language"],
                score=hit["_score"]
            )
            for hit in result["hits"]["hits"]
        ]

    def search_wildcard(self, pattern: str, category: str = None) -> List[CategoryMatch]:
        """Wildcard search - use * and ? in pattern."""
        if self._auto_refresh:
            self._check_refresh_needed()

        query = {
            "bool": {
                "must": [
                    {"wildcard": {"term": pattern.lower()}},
                    {"term": {"dimension": "SUBJECT"}}
                ]
            }
        }
        if category:
            query["bool"]["must"].append({"term": {"category": category}})

        result = self.es.search(index=INDEX_NAME, body={"query": query, "size": 20})

        return [
            CategoryMatch(
                canonical=hit["_source"]["canonical"],
                category=hit["_source"]["category"],
                term=hit["_source"]["term"],
                language=hit["_source"]["language"],
                score=hit["_score"]
            )
            for hit in result["hits"]["hits"]
        ]

    def search_by_language(self, lang: str, category: str = None) -> List[CategoryMatch]:
        """Get all terms for a specific language."""
        query = {
            "bool": {
                "must": [
                    {"term": {"language": lang}},
                    {"term": {"dimension": "SUBJECT"}}
                ]
            }
        }
        if category:
            query["bool"]["must"].append({"term": {"category": category}})

        result = self.es.search(index=INDEX_NAME, body={"query": query, "size": 1000})

        return [
            CategoryMatch(
                canonical=hit["_source"]["canonical"],
                category=hit["_source"]["category"],
                term=hit["_source"]["term"],
                language=hit["_source"]["language"],
                score=hit["_score"]
            )
            for hit in result["hits"]["hits"]
        ]

    def search_all(
        self,
        query: str,
        category: str = None,
        methods: List[str] = None,
        top_k: int = 10
    ) -> Dict[str, List[CategoryMatch]]:
        """
        Run ALL search methods and return combined results.

        Methods: exact, fuzzy, prefix, semantic, hybrid
        """
        if methods is None:
            methods = ["exact", "fuzzy", "prefix", "semantic", "hybrid"]

        results = {}

        if "exact" in methods:
            results["exact"] = self.search_exact(query, category)

        if "fuzzy" in methods:
            results["fuzzy"] = self.search_fuzzy(query, category)

        if "prefix" in methods:
            results["prefix"] = self.search_prefix(query, category)

        if "semantic" in methods:
            results["semantic"] = self.search_semantic(query, category, top_k)

        if "hybrid" in methods:
            results["hybrid"] = self.search_hybrid(query, category, top_k)

        return results

    def search_json_direct(self, term: str, category: str = None) -> List[Dict]:
        """
        Search JSONs directly (no ES).
        Useful when ES is down or for offline use.
        """
        term_lower = term.lower()
        results = []

        categories = [category] if category else ["professions", "titles", "industries"]

        for cat in categories:
            cat_data = self.synonyms.get(cat, {})
            for canonical, langs in cat_data.items():
                for lang, terms in langs.items():
                    if not isinstance(terms, list):
                        continue
                    for t in terms:
                        if term_lower in t.lower() or t.lower() in term_lower:
                            results.append({
                                "canonical": canonical,
                                "category": cat,
                                "term": t,
                                "language": lang,
                                "match_type": "exact" if term_lower == t.lower() else "partial"
                            })

        return results

    # === Resolution ===

    def resolve(self, term: str, category: str = None) -> Optional[str]:
        """Resolve any term to its canonical form."""
        # Try exact first
        matches = self.search_exact(term, category)
        if matches:
            return matches[0].canonical

        # Fall back to semantic
        matches = self.search_semantic(term, category, top_k=1)
        return matches[0].canonical if matches else None

    def resolve_profession(self, term: str) -> Optional[str]:
        return self.resolve(term, category="professions")

    def resolve_title(self, term: str) -> Optional[str]:
        return self.resolve(term, category="titles")

    def resolve_industry(self, term: str) -> Optional[str]:
        return self.resolve(term, category="industries")

    # === Pattern Generation ===

    def get_extraction_patterns(self, category: str) -> List[tuple]:
        """
        Generate regex patterns for extraction.
        Returns [(canonical, pattern), ...]
        """
        import re

        patterns = []
        cat_data = self.synonyms.get(category, {})

        for canonical, langs in cat_data.items():
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

    def get_all_patterns(self) -> Dict[str, List[tuple]]:
        """Get patterns for all categories."""
        return {
            "professions": self.get_extraction_patterns("professions"),
            "titles": self.get_extraction_patterns("titles"),
            "industries": self.get_extraction_patterns("industries")
        }


# Singleton
_bridge = None

def get_subject_bridge() -> SubjectBridge:
    global _bridge
    if _bridge is None:
        _bridge = SubjectBridge()
    return _bridge
