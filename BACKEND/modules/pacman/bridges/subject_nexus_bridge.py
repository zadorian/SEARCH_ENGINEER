#!/usr/bin/env python3
"""
PACMAN Bridge to SUBJECT and NEXUS Modules

Provides:
1. Synonym lookup for extraction patterns
2. Embedding-based semantic matching
3. Pattern generation from ontologies

Usage:
    from PACMAN.bridges.subject_nexus_bridge import SubjectNexusBridge

    bridge = SubjectNexusBridge()

    # Get all synonyms for a profession
    synonyms = bridge.get_profession_synonyms("lawyer")  # All languages

    # Get extraction patterns
    patterns = bridge.get_extraction_patterns("professions")  # Regex patterns

    # Semantic match
    matches = bridge.semantic_match("rechtsanwalt", category="professions")
    # → [("lawyer", 0.95), ("attorney", 0.89), ...]
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

# Paths
DATA_ROOT = Path("/data")
CLASSES_DIR = DATA_ROOT / "CLASSES"
SUBJECT_DIR = CLASSES_DIR / "SUBJECT"
NEXUS_DIR = CLASSES_DIR / "NEXUS"

# SUBJECT files
SUBJECT_SYNONYMS = SUBJECT_DIR / "synonyms.json"
SUBJECT_EMBEDDINGS = SUBJECT_DIR / "subject_embeddings.json"
INDUSTRIES_FILE = SUBJECT_DIR / "industries.json"
PROFESSIONS_FILE = SUBJECT_DIR / "professions.json"
TITLES_FILE = SUBJECT_DIR / "titles.json"

# NEXUS files
NEXUS_SYNONYMS = NEXUS_DIR / "data" / "relationship_synonyms.json"
NEXUS_ONTOLOGY = NEXUS_DIR / "RELATIONSHIPS" / "ontology.json"


@dataclass
class SynonymMatch:
    """Result of synonym lookup."""
    canonical: str
    category: str
    language: str
    confidence: float
    matched_term: str


class SubjectNexusBridge:
    """
    Bridge between PACMAN extraction and SUBJECT/NEXUS ontologies.
    """

    def __init__(self, use_embeddings: bool = True):
        self._subject_synonyms = None
        self._nexus_synonyms = None
        self._subject_embeddings = None
        self._model = None
        self.use_embeddings = use_embeddings

    # === Lazy Loading ===

    @property
    def subject_synonyms(self) -> Dict:
        if self._subject_synonyms is None:
            self._subject_synonyms = self._load_json(SUBJECT_SYNONYMS)
        return self._subject_synonyms

    @property
    def nexus_synonyms(self) -> Dict:
        if self._nexus_synonyms is None:
            self._nexus_synonyms = self._load_json(NEXUS_SYNONYMS)
        return self._nexus_synonyms

    @property
    def subject_embeddings(self) -> Dict:
        if self._subject_embeddings is None and SUBJECT_EMBEDDINGS.exists():
            self._subject_embeddings = self._load_json(SUBJECT_EMBEDDINGS)
        return self._subject_embeddings

    def _load_json(self, path: Path) -> Dict:
        if not path.exists():
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    # === Synonym Lookup ===

    def get_profession_synonyms(self, canonical: str, lang: Optional[str] = None) -> List[str]:
        """Get all synonyms for a profession."""
        return self._get_synonyms("professions", canonical, lang)

    def get_title_synonyms(self, canonical: str, lang: Optional[str] = None) -> List[str]:
        """Get all synonyms for a title."""
        return self._get_synonyms("titles", canonical, lang)

    def get_industry_synonyms(self, canonical: str, lang: Optional[str] = None) -> List[str]:
        """Get all synonyms for an industry."""
        return self._get_synonyms("industries", canonical, lang)

    def get_relationship_synonyms(self, canonical: str, lang: Optional[str] = None) -> List[str]:
        """Get all synonyms for a relationship (from NEXUS)."""
        synonyms = self.nexus_synonyms.get("synonyms", {}).get(canonical, {})
        if lang:
            return synonyms.get(lang, [])
        # All languages
        all_syns = []
        for syns in synonyms.values():
            if isinstance(syns, list):
                all_syns.extend(syns)
        return all_syns

    def _get_synonyms(self, category: str, canonical: str, lang: Optional[str] = None) -> List[str]:
        """Generic synonym lookup."""
        cat_data = self.subject_synonyms.get(category, {}).get(canonical, {})
        if lang:
            return cat_data.get(lang, [])
        # All languages
        all_syns = []
        for lang_syns in cat_data.values():
            if isinstance(lang_syns, list):
                all_syns.extend(lang_syns)
        return all_syns

    # === Pattern Generation ===

    def get_extraction_patterns(self, category: str) -> List[str]:
        """
        Generate regex patterns from synonyms for PACMAN extraction.

        Returns patterns that match any synonym in any language.
        """
        patterns = []
        cat_data = self.subject_synonyms.get(category, {})

        for canonical, langs in cat_data.items():
            all_terms = []
            for lang_syns in langs.values():
                if isinstance(lang_syns, list):
                    all_terms.extend(lang_syns)

            if all_terms:
                # Escape special regex chars and join
                escaped = [re.escape(t) for t in all_terms if len(t) > 2]
                if escaped:
                    # Word boundary pattern
                    pattern = r'\b(' + '|'.join(escaped) + r')\b'
                    patterns.append((canonical, pattern))

        return patterns

    def get_all_extraction_patterns(self) -> Dict[str, List[Tuple[str, str]]]:
        """Get patterns for all categories (SUBJECT + NEXUS relationships)."""
        return {
            "professions": self.get_extraction_patterns("professions"),
            "titles": self.get_extraction_patterns("titles"),
            "industries": self.get_extraction_patterns("industries"),
            "relationships": self._get_relationship_patterns(),
        }

    def _get_relationship_patterns(self) -> List[Tuple[str, str]]:
        """Generate patterns from NEXUS relationship synonyms."""
        patterns = []
        for rel, langs in self.nexus_synonyms.get("synonyms", {}).items():
            all_terms = []
            for lang_syns in langs.values():
                if isinstance(lang_syns, list):
                    all_terms.extend(lang_syns)

            if all_terms:
                escaped = [re.escape(t) for t in all_terms if len(t) > 2]
                if escaped:
                    pattern = r'\b(' + '|'.join(escaped) + r')\b'
                    patterns.append((rel, pattern))

        return patterns

    # === Semantic Matching ===

    def semantic_match(
        self,
        term: str,
        category: Optional[str] = None,
        top_k: int = 5,
        threshold: float = 0.7
    ) -> List[SynonymMatch]:
        """
        Find best matches for a term using embeddings.

        Args:
            term: Input term to match
            category: Limit to specific category (professions/titles/industries)
            top_k: Return top K matches
            threshold: Minimum similarity threshold

        Returns:
            List of SynonymMatch objects sorted by confidence
        """
        if not self.use_embeddings or self.subject_embeddings is None:
            # Fallback to exact string matching
            return self._exact_match(term, category)

        # Load model lazily
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                model_name = self.subject_embeddings.get("meta", {}).get(
                    "model", "paraphrase-multilingual-MiniLM-L12-v2"
                )
                self._model = SentenceTransformer(model_name)
            except ImportError:
                return self._exact_match(term, category)

        # Embed query
        query_vec = self._model.encode(term.lower())

        # Search embeddings
        matches = []
        embeddings = self.subject_embeddings.get("embeddings", {})

        categories = [category] if category else ["professions", "titles", "industries"]

        for cat in categories:
            if cat not in embeddings:
                continue

            for canonical, data in embeddings[cat].items():
                # Check canonical embedding
                canon_vec = data.get("canonical_embedding", [])
                if canon_vec:
                    sim = self._cosine_similarity(query_vec, canon_vec)
                    if sim >= threshold:
                        matches.append(SynonymMatch(
                            canonical=canonical,
                            category=cat,
                            language="canonical",
                            confidence=float(sim),
                            matched_term=canonical
                        ))

                # Check synonym embeddings
                for lang, terms in data.get("synonyms", {}).items():
                    for syn_term, syn_vec in terms.items():
                        sim = self._cosine_similarity(query_vec, syn_vec)
                        if sim >= threshold:
                            matches.append(SynonymMatch(
                                canonical=canonical,
                                category=cat,
                                language=lang,
                                confidence=float(sim),
                                matched_term=syn_term
                            ))

        # Sort by confidence, return top_k
        matches.sort(key=lambda x: x.confidence, reverse=True)
        return matches[:top_k]

    def _exact_match(self, term: str, category: Optional[str] = None) -> List[SynonymMatch]:
        """Fallback exact string matching."""
        term_lower = term.lower()
        matches = []

        categories = [category] if category else ["professions", "titles", "industries"]

        for cat in categories:
            cat_data = self.subject_synonyms.get(cat, {})
            for canonical, langs in cat_data.items():
                for lang, syns in langs.items():
                    if not isinstance(syns, list):
                        continue
                    for syn in syns:
                        if term_lower == syn.lower():
                            matches.append(SynonymMatch(
                                canonical=canonical,
                                category=cat,
                                language=lang,
                                confidence=1.0,
                                matched_term=syn
                            ))
                        elif term_lower in syn.lower() or syn.lower() in term_lower:
                            matches.append(SynonymMatch(
                                canonical=canonical,
                                category=cat,
                                language=lang,
                                confidence=0.8,
                                matched_term=syn
                            ))

        matches.sort(key=lambda x: x.confidence, reverse=True)
        return matches[:5]

    def _cosine_similarity(self, vec1, vec2) -> float:
        """Compute cosine similarity between two vectors."""
        import numpy as np
        v1 = np.array(vec1)
        v2 = np.array(vec2)
        return float(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2)))

    # === Resolve Functions ===

    def resolve_profession(self, term: str) -> Optional[str]:
        """Resolve a term to canonical profession."""
        matches = self.semantic_match(term, category="professions", top_k=1)
        return matches[0].canonical if matches else None

    def resolve_title(self, term: str) -> Optional[str]:
        """Resolve a term to canonical title."""
        matches = self.semantic_match(term, category="titles", top_k=1)
        return matches[0].canonical if matches else None

    def resolve_industry(self, term: str) -> Optional[str]:
        """Resolve a term to canonical industry."""
        matches = self.semantic_match(term, category="industries", top_k=1)
        return matches[0].canonical if matches else None

    def resolve_relationship(self, term: str) -> Optional[str]:
        """Resolve a term to canonical relationship (from NEXUS)."""
        term_lower = term.lower()
        for rel, langs in self.nexus_synonyms.get("synonyms", {}).items():
            for syns in langs.values():
                if isinstance(syns, list) and term_lower in [s.lower() for s in syns]:
                    return rel
        return None


# Singleton instance
_bridge_instance = None


def get_bridge() -> SubjectNexusBridge:
    """Get singleton bridge instance."""
    global _bridge_instance
    if _bridge_instance is None:
        _bridge_instance = SubjectNexusBridge()
    return _bridge_instance


# Convenience functions
def get_profession_patterns() -> List[Tuple[str, str]]:
    """Get profession extraction patterns."""
    return get_bridge().get_extraction_patterns("professions")


def get_title_patterns() -> List[Tuple[str, str]]:
    """Get title extraction patterns."""
    return get_bridge().get_extraction_patterns("titles")


def get_industry_patterns() -> List[Tuple[str, str]]:
    """Get industry extraction patterns."""
    return get_bridge().get_extraction_patterns("industries")


def get_relationship_patterns() -> List[Tuple[str, str]]:
    """Get relationship extraction patterns (from NEXUS)."""
    return get_bridge()._get_relationship_patterns()


if __name__ == "__main__":
    # Test the bridge
    print("=== Testing SubjectNexusBridge ===")

    bridge = SubjectNexusBridge(use_embeddings=False)

    # Test synonym lookup
    print("\nLawyer synonyms (DE):")
    print(bridge.get_profession_synonyms("lawyer", "de"))

    print("\nCEO synonyms (all):")
    print(bridge.get_title_synonyms("ceo"))

    print("\nOfficer_of synonyms (EN):")
    print(bridge.get_relationship_synonyms("officer_of", "en"))

    # Test patterns
    print("\nProfession patterns:")
    patterns = bridge.get_extraction_patterns("professions")
    for canon, pat in patterns[:3]:
        print(f"  {canon}: {pat[:80]}...")

    # Test resolution
    print("\nResolve 'rechtsanwalt':", bridge.resolve_profession("rechtsanwalt"))
    print("Resolve 'geschäftsführer':", bridge.resolve_title("geschäftsführer"))
    print("Resolve 'membro del consiglio':", bridge.resolve_relationship("membro del consiglio"))

    print("\n=== Test complete ===")
