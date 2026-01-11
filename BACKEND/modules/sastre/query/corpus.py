"""
SASTRE Corpus Checker - Unknown Knowns detection.

CRITICAL: Before external search, check what we already HAVE.

"The old lady on the corner exists (Known), but we don't know she's relevant
(Unknown) until we discover she saw a green jacket. The Corpus holds her record
until that connection is made."

This implements Step 0 of any query: check corpus BEFORE external search.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import sys
from pathlib import Path


# =============================================================================
# CORPUS HIT
# =============================================================================

@dataclass
class CorpusHit:
    """A match found in the corpus."""
    source_id: str
    source_type: str  # wdc, cymonides, project
    match_type: str  # exact, fuzzy, partial
    relevance: float  # 0.0 - 1.0
    content_preview: str
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CorpusCheckResult:
    """Result of corpus check."""
    found_in_corpus: bool
    hits: List[CorpusHit]
    skip_external: bool  # If true, corpus answers the question
    enrich_existing: bool  # If true, found related entity to enrich
    total_hits: int = 0
    wdc_hits: int = 0
    project_hits: int = 0


# =============================================================================
# CORPUS CHECKER
# =============================================================================

class CorpusChecker:
    """
    Checks corpus for existing knowledge BEFORE external search.

    Sources checked:
    1. WDC indices (800M+ entities from Schema.org)
       - wdc-person-entities
       - wdc-organization-entities
       - wdc-localbusiness-entities
       - wdc-product-entities

    2. Project corpus (cymonides-1-{projectId})
       - All entities found in this investigation
       - Related investigations in same project

    3. Global corpus (if configured)
       - Cross-project entity matching
    """

    def __init__(self, wdc_client=None, cymonides_client=None, project_id: str = None):
        self.wdc_client = wdc_client
        self.cymonides_client = cymonides_client
        self.project_id = project_id
        self._lazy_loaded = False

    def _lazy_load(self):
        """Lazy load clients if not provided."""
        if self._lazy_loaded:
            return

        self._lazy_loaded = True

        # Try to load WDC client
        if not self.wdc_client:
            try:
                backend_path = Path(__file__).parent.parent.parent.parent
                if str(backend_path) not in sys.path:
                    sys.path.insert(0, str(backend_path))

                from DEFINITIONAL.wdc_query import WDCQueryService
                self.wdc_client = WDCQueryService()
            except ImportError:
                pass

    def check(
        self,
        query: str,
        entity_type: str = None,
        limit: int = 50
    ) -> CorpusCheckResult:
        """
        Check corpus for existing knowledge.

        This is Step 0 of any query: What do we already have?
        """
        self._lazy_load()

        hits = []
        wdc_hits = 0
        project_hits = 0

        # 1. Check WDC indices
        if self.wdc_client:
            wdc_results = self._check_wdc(query, entity_type, limit)
            hits.extend(wdc_results)
            wdc_hits = len(wdc_results)

        # 2. Check project corpus
        if self.cymonides_client and self.project_id:
            project_results = self._check_project(query, entity_type, limit)
            hits.extend(project_results)
            project_hits = len(project_results)

        # Analyze results
        found = len(hits) > 0
        skip_external = self._should_skip_external(hits, entity_type)
        enrich_existing = self._should_enrich(hits)

        return CorpusCheckResult(
            found_in_corpus=found,
            hits=hits,
            skip_external=skip_external,
            enrich_existing=enrich_existing,
            total_hits=len(hits),
            wdc_hits=wdc_hits,
            project_hits=project_hits,
        )

    def check_for_gap(self, gap: Any) -> CorpusCheckResult:
        """
        Check corpus for a specific gap.

        Uses gap's target_subject and target_location.
        """
        search_terms = []

        if hasattr(gap, 'target_subject') and gap.target_subject:
            search_terms.append(gap.target_subject)

        if hasattr(gap, 'target_location') and gap.target_location:
            search_terms.append(gap.target_location)

        if hasattr(gap, 'description') and gap.description:
            # Extract key terms from description
            keywords = self._extract_keywords(gap.description)
            search_terms.extend(keywords[:3])

        # Combine results from all search terms
        all_hits = []
        for term in search_terms:
            result = self.check(term)
            all_hits.extend(result.hits)

        # Deduplicate
        seen = set()
        unique_hits = []
        for hit in all_hits:
            key = (hit.source_id, hit.entity_id or hit.content_preview[:50])
            if key not in seen:
                seen.add(key)
                unique_hits.append(hit)

        return CorpusCheckResult(
            found_in_corpus=len(unique_hits) > 0,
            hits=unique_hits,
            skip_external=self._should_skip_external(unique_hits, None),
            enrich_existing=self._should_enrich(unique_hits),
            total_hits=len(unique_hits),
        )

    def _check_wdc(
        self,
        query: str,
        entity_type: str,
        limit: int
    ) -> List[CorpusHit]:
        """Check WDC indices."""
        if not self.wdc_client:
            return []

        hits = []

        try:
            # Determine which index to search
            if entity_type in ('person', 'p:'):
                results = self.wdc_client.search_person_entities(name=query, limit=limit)
            elif entity_type in ('company', 'c:', 'organization'):
                results = self.wdc_client.search_organization_entities(name=query, limit=limit)
            elif entity_type in ('email', 'e:'):
                results = self.wdc_client.search_by_email(query, exact=False, limit=limit)
            elif entity_type in ('phone', 't:'):
                results = self.wdc_client.search_by_phone(query, limit=limit)
            elif entity_type in ('domain', 'd:'):
                result = self.wdc_client.find_by_domain(query, limit=limit)
                results = result.get('results', [])
            else:
                # Generic search across all indices
                results = self.wdc_client.search_entities(query, limit=limit).get('results', [])

            for r in results:
                hits.append(CorpusHit(
                    source_id='wdc',
                    source_type='wdc',
                    match_type=r.get('match_type', 'fuzzy'),
                    relevance=r.get('score', 0.5),
                    content_preview=str(r.get('name', r.get('preview', '')))[:200],
                    entity_type=r.get('type'),
                    entity_id=r.get('id'),
                    metadata=r,
                ))

        except Exception as e:
            # Log but don't fail
            print(f"WDC check error: {e}")

        return hits

    def _check_project(
        self,
        query: str,
        entity_type: str,
        limit: int
    ) -> List[CorpusHit]:
        """Check project-specific corpus."""
        if not self.cymonides_client or not self.project_id:
            return []

        hits = []

        try:
            # Search project index
            results = self.cymonides_client.search_nodes(
                project_id=self.project_id,
                query=query,
                node_types=[entity_type] if entity_type else None,
                limit=limit,
            )

            for r in results.get('results', []):
                hits.append(CorpusHit(
                    source_id=f'cymonides-1-{self.project_id}',
                    source_type='project',
                    match_type='fuzzy',
                    relevance=r.get('score', 0.5),
                    content_preview=r.get('label', '')[:200],
                    entity_type=r.get('type'),
                    entity_id=r.get('id'),
                    metadata=r,
                ))

        except Exception as e:
            print(f"Project corpus check error: {e}")

        return hits

    def _should_skip_external(
        self,
        hits: List[CorpusHit],
        entity_type: str
    ) -> bool:
        """
        Should we skip external search because corpus answers the question?

        Skip if:
        - High-confidence exact match found
        - Multiple confirming sources
        """
        if not hits:
            return False

        # Check for high-confidence matches
        high_confidence = [h for h in hits if h.relevance > 0.9 and h.match_type == 'exact']
        if high_confidence:
            return True

        # Check for multiple confirming sources
        sources = set(h.source_type for h in hits)
        if len(sources) >= 2 and len(hits) >= 3:
            return True

        return False

    def _should_enrich(self, hits: List[CorpusHit]) -> bool:
        """
        Did we find an existing entity to enrich rather than create new?
        """
        # If we found project hits, we should enrich those
        project_hits = [h for h in hits if h.source_type == 'project']
        return len(project_hits) > 0

    def _extract_keywords(self, text: str) -> List[str]:
        """Extract key terms from text."""
        import re

        # Remove common words
        stop_words = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'for', 'in', 'on', 'at', 'to', 'of', 'and', 'or'}

        # Extract words
        words = re.findall(r'\b\w+\b', text.lower())

        # Filter
        keywords = [w for w in words if len(w) > 3 and w not in stop_words]

        # Also extract quoted strings
        quoted = re.findall(r'"([^"]+)"', text)
        keywords.extend(quoted)

        return keywords[:10]


# =============================================================================
# CONVENIENCE FUNCTION
# =============================================================================

def check_corpus_before_search(
    query: str,
    entity_type: str = None,
    project_id: str = None
) -> CorpusCheckResult:
    """
    Quick corpus check before external search.

    Usage:
        result = check_corpus_before_search("John Smith", "person", "my-project")
        if result.skip_external:
            # Use corpus hits instead
            return result.hits
        else:
            # Proceed with external search
            ...
    """
    checker = CorpusChecker(project_id=project_id)
    return checker.check(query, entity_type)
